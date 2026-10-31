import re
STOP = set("""a an the of to in on for and or is are was were be been by with at from as that this
these those it its what which who whom how when where why does do did shall must should can could
will would per than then into about after before under over between any all each our their there
i we you he she they them me my your if not no yes so such also only more most other some""".split())
TOKEN = re.compile(r"[A-Za-z]+-\d+|\d+(?:\.\d+)?|[A-Za-z][A-Za-z0-9]*")

def tokenize(text):
    return [t.lower() for t in TOKEN.findall(text) if t.lower() not in STOP]
