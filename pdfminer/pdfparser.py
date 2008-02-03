#!/usr/bin/env python

# pdfparser.py, Yusuke Shinyama
#  ver 0.1, Dec 24 2004-
#  ver 0.2, Dec 24 2007

# TODO:
#   - Code Documentation.
#   - Error handling for invalid type.

#   - Outlines.
#   - Named Objects. (pages)
#   - Writers.
#   - Linearized PDF.
#   - Encryption?

import sys
stderr = sys.stderr
from utils import choplist, nunpack
from psparser import PSException, PSSyntaxError, PSTypeError, PSEOF, \
     PSLiteral, PSKeyword, PSLiteralTable, PSKeywordTable, \
     literal_name, keyword_name, \
     PSStackParser, STRICT


##  PDF Exceptions
##
class PDFException(PSException): pass
class PDFSyntaxError(PDFException): pass
class PDFEncrypted(PDFException): pass
class PDFTypeError(PDFException): pass
class PDFValueError(PDFException): pass


# some predefined literals and keywords.
LITERAL_OBJSTM = PSLiteralTable.intern('ObjStm')
LITERAL_XREF = PSLiteralTable.intern('XRef')
LITERAL_PAGE = PSLiteralTable.intern('Page')
LITERAL_PAGES = PSLiteralTable.intern('Pages')
LITERAL_CATALOG = PSLiteralTable.intern('Catalog')
LITERAL_FLATE_DECODE = PSLiteralTable.intern('FlateDecode')
KEYWORD_R = PSKeywordTable.intern('R')
KEYWORD_OBJ = PSKeywordTable.intern('obj')
KEYWORD_ENDOBJ = PSKeywordTable.intern('endobj')
KEYWORD_STREAM = PSKeywordTable.intern('stream')
KEYWORD_XREF = PSKeywordTable.intern('xref')
KEYWORD_STARTXREF = PSKeywordTable.intern('startxref')


##  PDFObjRef
##
class PDFObjRef:
  
  def __init__(self, doc, objid, _):
    if objid == 0:
      if STRICT:
        raise PDFValueError('objid cannot be 0.')
    self.doc = doc
    self.objid = objid
    #self.genno = genno  # Never used.
    return

  def __repr__(self):
    return '<PDFObjRef:%d>' % (self.objid)

  def resolve(self):
    return self.doc.getobj(self.objid)


# resolve
def resolve1(x):
  '''
  Resolve an object. If this is an array or dictionary,
  it may still contains some indirect objects inside.
  '''
  while isinstance(x, PDFObjRef):
    x = x.resolve()
  return x

def resolveall(x):
  '''
  Recursively resolve X and all the internals.
  Make sure there is no indirect reference within the nested object.
  This procedure might be slow.
  '''
  while isinstance(x, PDFObjRef):
    x = x.resolve()
  if isinstance(x, list):
    x = [ resolveall(v) for v in x ]
  elif isinstance(x, dict):
    for (k,v) in x.iteritems():
      x[k] = resolveall(v)
  return x

# Type cheking
def int_value(x):
  x = resolve1(x)
  if not isinstance(x, int):
    if STRICT:
      raise PDFTypeError('integer required: %r' % x)
    return 0
  return x

def float_value(x):
  x = resolve1(x)
  if not isinstance(x, float):
    if STRICT:
      raise PDFTypeError('float required: %r' % x)
    return 0.0
  return x

def num_value(x):
  x = resolve1(x)
  if not (isinstance(x, int) or isinstance(x, float)):
    if STRICT:
      raise PDFTypeError('int or float required: %r' % x)
    return 0
  return x

def str_value(x):
  x = resolve1(x)
  if not isinstance(x, str):
    if STRICT:
      raise PDFTypeError('string required: %r' % x)
    return ''
  return x

def list_value(x):
  x = resolve1(x)
  if not (isinstance(x, list) or isinstance(x, tuple)):
    if STRICT:
      raise PDFTypeError('list required: %r' % x)
    return []
  return x

def dict_value(x):
  x = resolve1(x)
  if not isinstance(x, dict):
    if STRICT:
      raise PDFTypeError('dict required: %r' % x)
    return {}
  return x

def stream_value(x):
  x = resolve1(x)
  if not isinstance(x, PDFStream):
    if STRICT:
      raise PDFTypeError('stream required: %r' % x)
    return PDFStream({}, '')
  return x


##  PDFStream type
##
class PDFStream:
  
  def __init__(self, dic, rawdata, decipher=None):
    self.dic = dic
    self.rawdata = rawdata
    self.decipher = decipher
    self.data = None
    return
  
  def __repr__(self):
    return '<PDFStream: %r>' % (self.dic)

  def decode(self):
    assert self.data == None and self.rawdata != None
    data = self.rawdata
    if self.decipher:
      data = self.decipher(data)
    if 'Filter' not in self.dic:
      self.data = data
      self.rawdata = None
      return
    filters = self.dic['Filter']
    if not isinstance(filters, list):
      filters = [ filters ]
    for f in filters:
      if f == LITERAL_FLATE_DECODE:
        import zlib
        # will get errors if the document is encrypted.
        data = zlib.decompress(data)
        # apply predictors
        params = self.dic.get('DecodeParms', {})
        if 'Predictor' in params:
          pred = int_value(params['Predictor'])
          if pred:
            if pred != 12:
              raise PDFValueError('Unsupported predictor: %r' % pred)
            if 'Columns' not in params:
              raise PDFValueError('Columns undefined for predictor=12')
            columns = int_value(params['Columns'])
            buf = ''
            ent0 = '\x00' * columns
            for i in xrange(0, len(data), columns+1):
              pred = data[i]
              ent1 = data[i+1:i+1+columns]
              if pred == '\x02':
                ent1 = ''.join( chr((ord(a)+ord(b)) & 255) for (a,b) in zip(ent0,ent1) )
              buf += ent1
              ent0 = ent1
            data = buf
      else:
        if STRICT:
          raise PDFValueError('Invalid filter spec: %r' % f)
    self.data = data
    self.rawdata = None
    return

  def get_data(self):
    if self.data == None:
      self.decode()
    return self.data
  

##  PDFPage
##
class PDFPage:
  
  def __init__(self, doc, pageidx, attrs):
    self.doc = doc
    self.pageid = pageidx
    self.attrs = dict_value(attrs)
    self.lastmod = self.attrs.get('LastModified')
    self.resources = resolve1(self.attrs['Resources'])
    self.mediabox = resolve1(self.attrs['MediaBox'])
    if 'CropBox' in self.attrs:
      self.cropbox = resolve1(self.attrs['CropBox'])
    else:
      self.cropbox = self.mediabox
    self.rotate = self.attrs.get('Rotate', 0)
    self.annots = self.attrs.get('Annots')
    self.beads = self.attrs.get('B')
    contents = resolve1(self.attrs['Contents'])
    if not isinstance(contents, list):
      contents = [ contents ]
    self.contents = contents
    return

  def __repr__(self):
    return '<PDFPage: Resources=%r, MediaBox=%r>' % (self.resources, self.mediabox)


##  XRefs

##  PDFXRef
##
class PDFXRef:

  def __init__(self, parser):
    while 1:
      (_, line) = parser.nextline()
      if not line:
        if STRICT:
          raise PDFSyntaxError('premature eof: %r' % parser)
        break
      line = line.strip()
      f = line.split(' ')
      if len(f) != 2:
        if line != 'trailer':
          if STRICT:
            raise PDFSyntaxError('trailer not found: %r: line=%r' % (parser, line))
        break
      (start, nobjs) = map(long, f)
      self.objid0 = start
      self.objid1 = start+nobjs
      self.offsets = []
      for objid in xrange(start, start+nobjs):
        (_, line) = parser.nextline()
        f = line.strip().split(' ')
        if len(f) != 3:
          if STRICT:
            raise PDFSyntaxError('invalid xref format: %r, line=%r' % (parser, line))
          continue
        (pos, genno, use) = f
        self.offsets.append((int(genno), long(pos), use))
    # read trailer
    (_, dic) = parser.nextobject()
    self.trailer = dict_value(dic)
    return

  def getpos(self, objid):
    if objid < self.objid0 or self.objid1 <= objid:
      raise IndexError(objid)
    (genno, pos, use) = self.offsets[objid-self.objid0]
    if use != 'n':
      if STRICT:
        raise PDFValueError('unused objid=%r' % objid)
    return (None, pos)


##  PDFXRefStream
##
class PDFXRefStream:

  def __init__(self, parser):
    (_,objid) = parser.nextobject()
    (_,genno) = parser.nextobject()
    parser.nextobject()
    (_,stream) = parser.nextobject()
    if STRICT:
      if stream.dic['Type'] != LITERAL_XREF:
        raise PDFSyntaxError('invalid stream spec.')
    size = stream.dic['Size']
    (start, nobjs) = stream.dic.get('Index', (0,size))
    self.objid0 = start
    self.objid1 = start+nobjs
    (self.fl1, self.fl2, self.fl3) = stream.dic['W']
    self.data = stream.get_data()
    self.entlen = self.fl1+self.fl2+self.fl3
    self.trailer = stream.dic
    return

  def getpos(self, objid):
    if objid < self.objid0 or self.objid1 <= objid:
      raise IndexError(objid)
    i = self.entlen * (objid-self.objid0)
    ent = self.data[i:i+self.entlen]
    f1 = nunpack(ent[:self.fl1], 1)
    if f1 == 1:
      pos = nunpack(ent[self.fl1:self.fl1+self.fl2])
      genno = nunpack(ent[self.fl1+self.fl2:])
      return (None, pos)
    elif f1 == 2:
      objid = nunpack(ent[self.fl1:self.fl1+self.fl2])
      index = nunpack(ent[self.fl1+self.fl2:])
      return (objid, index)


##  PDFDocument
##
INHERITABLE_ATTRS = set(['Resources', 'MediaBox', 'CropBox', 'Rotate'])
class PDFDocument:
  
  def __init__(self, debug=0):
    self.debug = debug
    self.xrefs = []
    self.objs = {}
    self.parsed_objs = {}
    self.decipher = None
    self.root = None
    self.catalog = None
    self.parser = None
    return

  def set_parser(self, parser):
    if self.parser: return
    self.parser = parser
    self.xrefs = list(parser.read_xref())
    for xref in self.xrefs:
      trailer = xref.trailer
      if 'Encrypt' in trailer:
        raise PDFEncrypted
        param = dict_value(trailer['Encrypt'])
        self.decipher = DECRYPTOR(param)
        self.parser.strfilter = self.decipher
      if 'Root' in trailer:
        self.set_root(dict_value(trailer['Root']))
        break
    else:
      raise PDFValueError('no /Root object!')
    return

  def getobj(self, objid):
    #assert self.xrefs
    if objid in self.objs:
      obj = self.objs[objid]
    else:
      for xref in self.xrefs:
        try:
          (strmid, index) = xref.getpos(objid)
          break
        except IndexError:
          pass
      else:
        if STRICT:
          raise PDFValueError('Cannot locate objid=%r' % objid)
        return None
      if strmid:
        stream = stream_value(self.getobj(strmid))
        if stream.dic['Type'] != LITERAL_OBJSTM:
          if STRICT:
            raise PDFSyntaxError('Not a stream object: %r' % stream)
        try:
          n = stream.dic['N']
        except KeyError:
          if STRICT:
            raise PDFSyntaxError('N is not defined: %r' % stream)
          n = 0
        if strmid in self.parsed_objs:
          objs = self.parsed_objs[stream]
        else:
          parser = PDFObjStrmParser(self, stream.get_data(), debug=self.debug)
          objs = []
          try:
            while 1:
              (_,obj) = parser.nextobject()
              objs.append(obj)
          except PSEOF:
            pass
          self.parsed_objs[stream] = objs
        obj = objs[stream.dic['N']*2+index]
      else:
        self.parser.seek(index)
        (_,objid1) = self.parser.nextobject() # objid
        (_,genno1) = self.parser.nextobject() # genno
        (_,kwd) = self.parser.nextobject()
        if kwd != KEYWORD_OBJ:
          raise PDFSyntaxError('invalid obj spec: offset=%r' % index)
        (_,obj) = self.parser.nextobject()
      if 2 <= self.debug:
        print >>stderr, 'register: objid=%r: %r' % (objid, obj)
      self.objs[objid] = obj
    return obj
  
  def get_pages(self, debug=0):
    #assert self.xrefs
    def search(obj, parent):
      tree = dict_value(obj).copy()
      for (k,v) in parent.iteritems():
        if k in INHERITABLE_ATTRS and k not in tree:
          tree[k] = v
      if tree['Type'] == LITERAL_PAGES:
        if 1 <= debug:
          print >>stderr, 'Pages: Kids=%r' % tree['Kids']
        for c in tree['Kids']:
          for x in search(c, tree):
            yield x
      elif tree['Type'] == LITERAL_PAGE:
        if 1 <= debug:
          print >>stderr, 'Page: %r' % tree
        yield tree
    for (i,tree) in enumerate(search(self.catalog['Pages'], self.catalog)):
      yield PDFPage(self, i, tree)
    return 

  def set_root(self, root):
    self.root = root
    self.catalog = dict_value(self.root)
    if self.catalog['Type'] != LITERAL_CATALOG:
      if STRICT:
        raise PDFValueError('Catalog not found!')
    self.outline = self.catalog.get('Outline')
    return
  

##  PDFParser
##
class PDFParser(PSStackParser):

  def __init__(self, doc, fp, debug=0):
    PSStackParser.__init__(self, fp, debug=debug)
    self.doc = doc
    self.doc.set_parser(self)
    return

  def __repr__(self):
    return '<PDFParser>'

  def do_keyword(self, pos, token):
    if token in (KEYWORD_XREF, KEYWORD_STARTXREF):
      self.add_results(*self.pop(1))
      return
    if token == KEYWORD_ENDOBJ:
      self.add_results(*self.pop(4))
      return
    
    if token == KEYWORD_R:
      # reference to indirect object
      try:
        ((_,objid), (_,genno)) = self.pop(2)
        (objid, genno) = (int(objid), int(genno))
        obj = PDFObjRef(self.doc, objid, genno)
        self.push((pos, obj))
      except PSSyntaxError:
        pass
      return
      
    if token == KEYWORD_STREAM:
      # stream object
      ((_,dic),) = self.pop(1)
      dic = dict_value(dic)
      try:
        objlen = int_value(dic['Length'])
      except KeyError:
        if STRICT:
          raise PDFValueError('/Length is undefined: %r' % dic)
        objlen = 0
      self.seek(pos)
      (_, line) = self.nextline()  # 'stream'
      pos += len(line)
      self.fp.seek(pos)
      data = self.fp.read(objlen)
      self.seek(pos+objlen)
      while 1:
        (linepos, line) = self.nextline()
        if line.startswith('endstream'): break
        objlen += len(line)
        data += line
      if 1 <= self.debug:
        print >>stderr, 'Stream: pos=%d, objlen=%d, dic=%r, data=%r...' % \
              (pos, objlen, dic, data[:10])
      obj = PDFStream(dic, data, self.doc.decipher)
      self.push((pos, obj))
      return
    
    # others
    self.push((pos, token))
    return

  def find_xref(self):
    # find the first xref table
    prev = None
    for line in self.revreadlines():
      line = line.strip()
      if 2 <= self.debug:
        print >>stderr, 'find_xref: %r' % line
      if line == 'startxref': break
      if line:
        prev = line
    else:
      if STRICT:
        raise PDFSyntaxError('startxref not found!')
      prev = 0
    if 1 <= self.debug:
      print >>stderr, 'xref found: pos=%r' % prev
    self.seek(long(prev))
    return

  # read xref tables and trailers
  def read_xref(self):
    self.find_xref()
    while 1:
      # read xref table
      (linepos, line) = self.nextline()
      if 2 <= self.debug:
        print >>stderr, 'read_xref: %r' % line
      if line[0].isdigit():
        # XRefStream: PDF-1.5
        self.seek(linepos)
        self.reset()
        xref = PDFXRefStream(self)
      else:
        if line.strip() != 'xref':
          if STRICT:
            raise PDFSyntaxError('xref not found: linepos=%d, line=%r' %
                                 (linepos, line))
        xref = PDFXRef(self)
      yield xref
      trailer = xref.trailer
      if 1 <= self.debug:
        print >>stderr, 'trailer: %r' % trailer
      if 'XRefStm' in trailer:
        self.seek(int_value(trailer['XRefStm']))
      if 'Prev' in trailer:
        # find previous xref
        pos = int_value(trailer['Prev'])
        self.seek(pos)
        if 1 <= self.debug:
          print >>stderr, 'prev trailer: pos=%d' % pos
      else:
        break
    return

##  PDFObjStrmParser
##
class PDFObjStrmParser(PDFParser):
  def __init__(self, doc, data, debug=0):
    try:
      from cStringIO import StringIO
    except ImportError:
      from StringIO import StringIO
    PDFParser.__init__(self, doc, StringIO(data), debug=debug)
    return
  
  def flush(self):
    self.add_results(*self.popall())
    return
