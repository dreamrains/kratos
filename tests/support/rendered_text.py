"""Read visible Markdown text/tables for presentation assertions only."""
from html.parser import HTMLParser
from decimal import Decimal, InvalidOperation
import mistune

class _Visible(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.tables=[]; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.table=[];self.tables.append(self.table)
        elif tag=='tr':self.row=[]
        elif tag in {'td','th'}:self.cell=[]
    def handle_data(self,data):
        self.parts.append(data)
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in {'td','th'} and self.cell is not None:
            if self.row is not None:self.row.append(''.join(self.cell))
            self.cell=None
        elif tag=='tr' and self.row is not None:
            if self.table is not None:self.table.append(self.row)
            self.row=None
        elif tag=='table':self.table=None

def _read(markdown):
    result=_Visible();result.feed(mistune.create_markdown(plugins=['table'])(markdown));return result

def visible_text(markdown):return ''.join(_read(markdown).parts)
def table_rows(markdown):return _read(markdown).tables

def has_pair(markdown,label,value):
    return any(row==[label,value] for table in table_rows(markdown) for row in table)

def _same_number(cell,value):
    try:return Decimal(cell.split('（',1)[0].split(' ',1)[0])==Decimal(str(value))
    except InvalidOperation:return False


def has_number(markdown,label,value):
    for table in table_rows(markdown):
        if any(len(row)==2 and row[0]==label and _same_number(row[1],value) for row in table):return True
        if table and label in table[0]:
            column=table[0].index(label)
            if any(len(row)>column and _same_number(row[column],value) for row in table[1:]):return True
    # Scalar host facts remain valid outside a multi-claim table.
    import re
    pattern=re.escape(label)+r'：([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)'
    return any(Decimal(m)==Decimal(str(value)) for m in re.findall(pattern,visible_text(markdown)))


def has_numeric_literal(markdown, value):
    """Find a visible numeric value without treating opaque IDs as numbers."""
    import re
    text = ' '.join(_read(markdown).parts)
    pattern = (r'(?<![A-Za-z0-9_.])'
               r'[+-]?(?:\d{1,3}(?:,\d{3})+(?:\.\d*)?|\d+(?:\.\d*)?|\.\d+)'
               r'(?:[eE][+-]?\d+)?(?![A-Za-z0-9_.])')
    expected = Decimal(str(value))
    return any(Decimal(token.replace(',', '')) == expected
               for token in re.findall(pattern, text))


def has_record(markdown,expected):
    def equal(cell,value):
        if type(value) in {int,float}:return _same_number(cell,value)
        shown='未知' if value is None else 'true' if value is True else 'false' if value is False else str(value)
        return cell==shown
    for table in table_rows(markdown):
        if not table or not all(key in table[0] for key in expected):continue
        columns={key:table[0].index(key) for key in expected}
        if any(all(len(row)>col and equal(row[col],expected[key]) for key,col in columns.items()) for row in table[1:]):return True
    return False

def has_matrix_cell(markdown,row_label,column_label,value):
    for table in table_rows(markdown):
        if not table or column_label not in table[0][1:]:continue
        column=table[0].index(column_label)
        if any(row and row[0]==row_label and len(row)>column and row[column]==value for row in table[1:]):return True
    return False
