"""Offline raw-archive inventory. No inference, extraction, training or network."""
import argparse,io,json,zipfile,hashlib
from pathlib import Path
from xml.etree import ElementTree as ET
from pipeline import ROOT
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def xlsx_preview(blob):
 with zipfile.ZipFile(io.BytesIO(blob)) as z:
  strings=[]
  if 'xl/sharedStrings.xml' in z.namelist():
   root=ET.fromstring(z.read('xl/sharedStrings.xml'))
   strings=[''.join(e.itertext()) for e in root.findall('s:si',NS)]
  sheets=[]
  for name in z.namelist():
   if not (name.startswith('xl/worksheets/sheet') and name.endswith('.xml')):continue
   root=ET.fromstring(z.read(name));rows=[]
   for r in root.findall('s:sheetData/s:row',NS)[:12]:
    cells=[]
    for cell in r.findall('s:c',NS):
     value=cell.find('s:v',NS);text=value.text if value is not None else ''.join(cell.itertext())
     if cell.get('t')=='s' and text is not None:text=strings[int(text)]
     cells.append(dict(column=cell.get('r'),value=text))
    rows.append(cells)
   sheets.append(dict(part=name,preview_rows=rows))
  return sheets

def inventory(path):
 out=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),files=[])
 with zipfile.ZipFile(path) as z:
  for item in z.infolist():
   record=dict(name=item.filename,bytes=item.file_size)
   if item.filename.lower().endswith('.xlsx'):record['sheets']=xlsx_preview(z.read(item))
   elif item.filename.lower().endswith(('.txt','.csv','.md')):record['preview']=z.read(item)[:6000].decode('utf-8',errors='replace')
   elif item.filename.lower().endswith('.xls'):record['status']='Legacy binary Excel: needs a separately approved parser; no guessed headers'
   out['files'].append(record)
 return out

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--output',type=Path,default=ROOT/'reports/phase4/raw_inventory.json');a=p.parse_args()
 result=inventory(a.archive);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2));print(a.output)
if __name__=='__main__':main()
