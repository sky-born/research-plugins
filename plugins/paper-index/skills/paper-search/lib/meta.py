# -*- coding: utf-8 -*-
"""Extracting title, author, year, journal and DOI.

All of these are automatic guesses. Always check against the source PDF before confirming a citation.
"""
import os, re

def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

JUNK = re.compile(
    r"^(https?://|www\.|doi\s*[:.]|10\.\d{4,9}/|©|Ó|\(c\)\s*\d|ISSN|ISBN|"
    r"Received|Revised|Accepted|Published|Available online|Manuscript|Article history|"
    r"Contents lists|journal homepage|ScienceDirect|ELSEVIER|Elsevier|Springer|"
    r"PHYSICAL REVIEW|Journal of [A-Z ]+,|Journal of ELECTRONIC|J Mater Sci|Materials Transactions|"
    r"Acta Materialia|Intermetallics|Microelectronics Reliability|Materials Science and Engineering [A-Z]|"
    r"Regular Issue Paper|RESEARCH ARTICLE|Research Article|ORIGINAL|Original|Open Access|open access|"
    r"Check for updates|check for updates|OPEN|Article\b|ARTICLE\b|REVIEW\b|Review Article|"
    r"Vol\.|VOLUME|Volume|No\.\s*\d|NUMBER|pp\.|\d{4}\s*[-–]\s*I?$|\d+\s*\(\d{4}\)|[\d\s\-–,.:;()]+$|"
    r"The Minerals|TMS\b|IEEE\b|MDPI|Materials\s*$|materials\s*$|Metals\s*$|metals\s*$|Crystals\s*$|"
    r"This article|Supplementary|SUPPLEMENTARY|Abstract|ABSTRACT|Keywords|KEYWORDS|Corresponding|"
    r"Cite this|How to cite|Citation|Special Issue|SPECIAL|Downloaded|View Online|Export Citation|"
    r"CrossMark|Article Type|Publication|Copyright|All rights|Print\b|Online\b|\d{1,2}\s+\w+\s+\d{4}$)")

AUTHORLINE = re.compile(
    r"(^[A-Z][a-zA-Z\-’']+\s+[A-Z]\.?\s*[A-Z]?\.?\s*[A-Z][a-zA-Z\-’']+\s*[\d*,†‡§]*\s*(,|and|$))"
    r"|(^[A-Z][A-Z\-’'\. ]{4,}\s*,?\s*\d*\s*(and|,|$))"
    r"|(\band\b\s+[A-Z][a-zA-Z\-’']+\s*[\d*]*\s*$)"
    r"|(^[A-Z][a-zA-Z\-’']+\s+[A-Z][a-zA-Z\-’']+[\d*,†‡§]+)"
    r"|(Department of|Institute|School of|University|Univ\.|College of|Laboratory|Co\.,|Corporation|Inc\.)")

HEADERISH = re.compile(
    r"(Vol\.\s*\d|No\.\s*\d,|\(\d{4}\)\s*(pp\.|\d+[–-]\d+)|\b\d{3,4}\s*\(\d{4}\)\s*\d+|"
    r"^Journal of [A-Z ]+,|^J Mater Sci.*\(\d{4}\)|Conference \(ECTC\)|^IEEE \d|"
    r"date of current version|^Materials and Engineering|^\d|"
    r"^DOI\b|^https?://|^doi\.org|\bTMS\s*$|\d{4}\s+TMS\b|"
    r"^[A-Z][A-Za-z .&]+\s+\d+\s*\(\d{4}\)|^[A-Z][A-Za-z .&]+,?\s+Vol|"
    r"\(\d{4}\)\s*\d+\s*:|^Journal of .{0,60}\(\d{4}\)|^[A-Z][A-Za-z:& .]+\s+\d{1,3}\s*\(\d{4}\)|"
    r"\bet al\.\s+\w+.{0,40}\(\d{4}\)|"
    r"\bEdited by\b|^Proceedings\b|^Contents\b|^Author Index\b)", re.I)

AUTHTAIL = re.compile(
    r"\s+([A-Z]\.\s*[A-Z]?\.?\s*[A-Z][a-z]+|[A-Z][a-z]+\s+[a-z]\s*[,⁎*]|"
    r"[A-Z]\.[A-Z]\.\s*[A-Z][a-z]+|,\s*[A-Z]\.\s)")

STOPX = re.compile(
    r"(\s+Received\b|\s+Accepted\b|\s+Department\b|\s+Institute\b|\s+School of\b|\s+University\b|"
    r"\s+Center for\b|\s+ABSTRACT\b|\s+Abstract\b|\s+Keywords\b|\s+\(Received|\s+https?://|"
    r"\s+Available online|\s+This article)")

ACRONYMS = {
    "IMC","IMCS","PCB","ENIG","ENEPIG","OSP","SAC","BGA","LTS","EM","XRD","SEM","EDS","TEM","DSC",
    "CTE","HPC","AI","RDL","DC","JEDEC","IPC","IEEE","UBM","CALPHAD","SMT","TIM","3D","2D","5D",
    "APT","JIM","TMS","USA","UV","CNN","AND","OF","THE","FOR","IN","ON","A","I","II","III","IV",
    "LSW","FDR","HRR","TSV","WLP","MEMS","LED","NMR","FIB","EBSD","AFM","DFT","MD","FEA","FEM",
    "ASTM","JIS","ISO","DNA","RNA","PCR","XPS","SAXS","NMR","HRTEM","STEM","EDX","WDS",
}

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)")
YEAR_RE = re.compile(r"\b(19[3-9]\d|20[0-3]\d)\b")

DOI_PUB = [
    (r"^10\.1016/j\.jallcom", "Journal of Alloys and Compounds"),
    (r"^10\.1016/j\.msea", "Materials Science and Engineering: A"),
    (r"^10\.1016/j\.mtadv", "Materials Today Advances"),
    (r"^10\.1016/j\.jmrt", "Journal of Materials Research and Technology"),
    (r"^10\.1016/j\.microrel", "Microelectronics Reliability"),
    (r"^10\.1016/j\.matchar", "Materials Characterization"),
    (r"^10\.1016/j\.actamat", "Acta Materialia"),
    (r"^10\.1016/j\.scriptamat", "Scripta Materialia"),
    (r"^10\.1016/j\.matdes", "Materials & Design"),
    (r"^10\.1016/j\.matlet", "Materials Letters"),
    (r"^10\.1016/j\.calphad", "Calphad"),
    (r"^10\.1016/j\.intermet", "Intermetallics"),
    (r"^10\.1016/j\.apsusc", "Applied Surface Science"),
    (r"^10\.1016/j\.tsf", "Thin Solid Films"),
    (r"^10\.1016/j\.surfcoat", "Surface and Coatings Technology"),
    (r"^10\.1016/j\.jmapro", "Journal of Manufacturing Processes"),
    (r"^10\.1016/j\.mtcomm", "Materials Today Communications"),
    (r"^10\.1016/j\.electacta", "Electrochimica Acta"),
    (r"^10\.1016/j\.corsci", "Corrosion Science"),
    (r"^10\.1016/j\.mssp", "Mater. Sci. Semicond. Process."),
    (r"^10\.1016/j\.mee", "Microelectronic Engineering"),
    (r"^10\.1016/", "Elsevier (other)"),
    (r"^10\.1007/s10854", "J. Mater. Sci.: Mater. Electron."),
    (r"^10\.1007/s11664", "Journal of Electronic Materials"),
    (r"^10\.1007/s11661", "Metall. Mater. Trans. A"),
    (r"^10\.1007/s11663", "Metall. Mater. Trans. B"),
    (r"^10\.1007/s10853", "Journal of Materials Science"),
    (r"^10\.1007/s11837", "JOM"),
    (r"^10\.1007/s11669", "J. Phase Equilib. Diffus."),
    (r"^10\.1007/", "Springer (other)"),
    (r"^10\.3390/ma\d", "Materials (MDPI)"),
    (r"^10\.3390/met", "Metals (MDPI)"),
    (r"^10\.3390/cryst", "Crystals (MDPI)"),
    (r"^10\.3390/mi", "Micromachines (MDPI)"),
    (r"^10\.3390/app", "Applied Sciences (MDPI)"),
    (r"^10\.3390/nano", "Nanomaterials (MDPI)"),
    (r"^10\.3390/", "MDPI (other)"),
    (r"^10\.1109/ECTC", "IEEE ECTC"),
    (r"^10\.1109/TCPMT", "IEEE Trans. CPMT"),
    (r"^10\.1109/JSSC", "IEEE J. Solid-State Circuits"),
    (r"^10\.1109/TDMR", "IEEE Trans. Device Mater. Reliab."),
    (r"^10\.1109/IEDM", "IEEE IEDM"),
    (r"^10\.1109/", "IEEE (other)"),
    (r"^10\.1103/PhysRevB", "Physical Review B"),
    (r"^10\.1103/PhysRevLett", "Physical Review Letters"),
    (r"^10\.1103/", "Physical Review (other)"),
    (r"^10\.1063/", "AIP (J. Appl. Phys. etc.)"),
    (r"^10\.1080/", "Taylor & Francis"),
    (r"^10\.1002/", "Wiley"),
    (r"^10\.1361/", "J. Phase Equilib."),
    (r"^10\.1149/", "J. Electrochem. Soc."),
    (r"^10\.1557/", "MRS / J. Mater. Res."),
    (r"^10\.2320/", "Materials Transactions (JIM)"),
    (r"^10\.1179/", "Taylor & Francis"),
    (r"^10\.1108/", "Soldering & SMT"),
    (r"^10\.1038/", "Nature family"),
    (r"^10\.1126/", "Science"),
    (r"^10\.1021/", "ACS"),
    (r"^10\.1039/", "RSC"),
    (r"^10\.6117/", "J. Microelectron. Packag. Soc. (KMEPS)"),
    (r"^10\.1201/", "CRC Press (book)"),
]

HEAD_JOURNALS = [
    "J Mater Sci: Mater Electron", "Journal of Materials Science: Materials in Electronics",
    "Journal of Alloys and Compounds", "Journal of ELECTRONIC MATERIALS", "Journal of Electronic Materials",
    "Microelectronics Reliability", "Materials Science and Engineering A", "Acta Materialia",
    "Scripta Materialia", "Metallurgical and Materials Transactions", "Materials Transactions",
    "Intermetallics", "Thin Solid Films", "Applied Surface Science", "Physical Review B",
    "Journal of The Electrochemical Society", "Journal of Materials Science",
    "Electronic Components and Technology Conference",
]


def extract_title(body):
    lines = [clean(l) for l in body[:8000].splitlines()]
    cand = []
    for l in lines[:70]:
        if not l:
            if cand:
                break
            continue
        if len(l) < 6 or JUNK.match(l):
            if cand:
                break
            continue
        if AUTHORLINE.search(l):
            if cand:
                break
            continue
        cand.append(l)
        if sum(len(x) for x in cand) > 150:
            break
    return re.sub(r"\s*[\d*,†‡§]+\s*$", "", clean(" ".join(cand)))


def filename_title(fn):
    b = re.sub(r"-(19|20)\d{2}-.*$", "", os.path.splitext(fn)[0])
    b = re.sub(r"^[A-ZÀ-ÿ][A-Za-zÀ-ÿ'’]{1,19}-", "", b)
    b = re.sub(r"_supplement.*$", "", b)
    b = re.sub(r"_\d+$", "", b)
    return clean(b.replace("_", " "))


def strip_author_tail(t):
    m = AUTHTAIL.search(t)
    if m and m.start() > 20:
        t = t[:m.start()]
    toks = t.split()
    for i, w in enumerate(toks):
        core = re.sub(r"[^A-Za-z]", "", w)
        if len(core) >= 3 and core.isupper() and core.upper() not in ACRONYMS and i > 2:
            return " ".join(toks[:i])
    return t


def _loose(pre):
    toks = [t for t in re.split(r"\W+", pre) if t]
    return re.compile(r"\W+".join(re.escape(t) for t in toks), re.I)


def extend_from_body(title, body):
    """Find a truncated title taken from the file name in the body text and extend it."""
    t = title.rstrip(" …").strip()
    if len(t.split()) < 3:
        return title, False
    flat = re.sub(r"\s+", " ", body)
    for L in (44, 32, 22):
        pre = t[:L]
        if len(pre.split()) < 3:
            break
        m = _loose(pre).search(flat)
        if not m:
            continue
        seg = flat[m.start():m.start() + 250]
        sm = STOPX.search(seg)
        if sm:
            seg = seg[:sm.start()]
        seg = strip_author_tail(seg.strip(" ,.-·")).strip(" ,.-·")
        seg = re.sub(r"\s*[\d*,†‡§⁎]+$", "", seg).strip(" ,.-·")
        if len(seg) > len(t) + 3 and len(seg) < 250:
            return seg, True
        break
    return title, False


def journal_from(doi, head):
    if doi:
        for pat, name in DOI_PUB:
            if re.search(pat, doi, re.I):
                return name
    h = head[:1500]
    for name in HEAD_JOURNALS:
        if name.lower() in h.lower():
            return name
    if re.search(r"Electronic Components and Technology Conference|\bECTC\b", h, re.I):
        return "IEEE ECTC"
    return ""


def build(rel, fn, folder, body):
    """Build the metadata of one paper."""
    head = body[:4000]
    m = re.match(r"^([A-ZÀ-ÿ][A-Za-zÀ-ÿ'’]{1,19})-", fn)
    author = m.group(1) if m else ""
    if author.upper() in ("J", "IPC", "JEDEC"):
        author = ""
    year = folder if re.fullmatch(r"(19|20)\d{2}", folder) else ""
    if not year:
        ys = YEAR_RE.findall(head)
        year = max(ys) if ys else ""
    dm = DOI_RE.search(head)
    doi = dm.group(1).rstrip(".,;)") if dm else ""

    t = extract_title(body)
    src = "pdf"
    if HEADERISH.search(t) or len(t) < 18:
        ft = filename_title(fn)
        if len(ft) >= 10:
            t, src = ft, "filename"
    if src == "filename" and body:
        t2, ok = extend_from_body(t, body)
        if ok:
            t, src = t2, "pdf(extended)"
    t = strip_author_tail(t).strip(" ,.-·")
    t = re.sub(r"\s*[\d*,†‡§⁎]+$", "", t).strip(" ,.-·")
    if len(t) > 190:
        t = t[:190].rsplit(" ", 1)[0] + " …"
    if not t:
        t = filename_title(fn) or fn
    if src == "filename":
        t = t.rstrip(" …") + " …"

    return dict(rel=rel, folder=folder, file=fn, year=year, author=author,
                title=t, title_src=src, doi=doi,
                journal=journal_from(doi, head), chars=len(body), note="")
