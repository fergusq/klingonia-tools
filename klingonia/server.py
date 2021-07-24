import re
from typing import Any, Callable, Dict, List, Set

from aiohttp import web
import aiohttp_jinja2
import jinja2
import yajwiz
from yajwiz.boqwiz import BoqwizEntry

import logging

from . import locales

logging.basicConfig(level=logging.INFO)

routes = web.RouteTableDef()

@routes.get('/')
@routes.get('/index/{lang}')
@routes.get('/index/{lang}/')
@aiohttp_jinja2.template("index.jinja2")
async def get_proofread(request):
    lang = request.match_info.get("lang", "en")
    return {"lang": locales.locale_map[lang], "path": "/index"}

@routes.get('/proofread')
@routes.get('/proofread/')
@routes.get('/proofread/{lang}')
@routes.get('/proofread/{lang}/')
@aiohttp_jinja2.template("proofreader.jinja2")
async def get_proofread(request):
    lang = request.match_info.get("lang", "en")
    return {"lang": locales.locale_map[lang], "path": "/proofread", "input": "", "result": ""}

@routes.post("/proofread")
@routes.post("/proofread/{lang}")
@aiohttp_jinja2.template("proofreader.jinja2")
async def post_proofread(request):
    lang = request.match_info.get("lang", "en")
    query = await request.post()
    if "text" not in query:
        raise web.HTTPBadRequest()
    
    n_errors, render = check_and_render(query["text"])
    return {"lang": locales.locale_map[lang], "path": "/proofread", "input": query["text"], "result": render, "no_errors": n_errors == 0}

def check_and_render(text: str):
    errors = yajwiz.get_errors(text)
    errors.sort(key=lambda e: e.location)
    ans = ""
    i = 0
    for error in errors:
        ans += text[i:error.location]
        if " " not in text[error.location:]:
            ans += f'<span class=error title="{error.message}">{text[error.location:]}</span>'
            return len(errors), ans

        i = text.index(" ", error.location)
        ans += f'<span class=error title="{error.message}">{text[error.location:i]}</span>'
    
    ans += text[i:]
    return len(errors), ans

@routes.get('/dictionary')
@routes.get('/dictionary/')
@routes.get('/dictionary/{lang}')
@routes.get('/dictionary/{lang}/')
@aiohttp_jinja2.template("dictionary.jinja2")
async def get_dictionary(request: web.Request):
    lang = request.match_info.get("lang", "en")
    query = request.query.get("q", "")
    return {"lang": locales.locale_map[lang], "path": "/dictionary", "input": query, "result": dictionary_query(query, lang), "boqwiz_version": dictionary.version}

dictionary = yajwiz.load_dictionary()

QUERY_OPERATORS: Dict[str, Callable[[BoqwizEntry, str], Any]] = {
    "tlh": lambda entry, arg: re.search(fix_xifan(arg), entry.name),
    "notes": lambda entry, arg: re.search(arg, entry.notes.get("en", "")),
    "ex": lambda entry, arg: re.search(arg, entry.examples.get("en", "")),
    "pos": lambda entry, arg: set(arg.split(",")) < set(re.split(r"[:,]", entry.part_of_speech)),
    "antonym": lambda entry, arg: re.search(fix_xifan(arg), entry.antonyms),
    "synonym": lambda entry, arg: re.search(fix_xifan(arg), entry.synonyms),
    "components": lambda entry, arg: re.search(fix_xifan(arg), entry.components),
    "see": lambda entry, arg: re.search(fix_xifan(arg), entry.see_also),
}

def add_operators(language: str):
    QUERY_OPERATORS[language] = lambda entry, arg: (re.search(arg, entry.definition[language]) or arg in entry.search_tags.get(language, []))
    QUERY_OPERATORS[language+"notes"] = lambda entry, arg: re.search(arg, entry.notes.get(language, ""))
    QUERY_OPERATORS[language+"ex"] = lambda entry, arg: re.search(arg, entry.examples.get(language, ""))

for language in dictionary.locales:
    add_operators(language)

def dictionary_query(query: str, lang: str):
    """
    Dictionary query:
    1. Analyze it whole as a Klingon word
    2. Split at spaces and analyze each word
    3. Parse text as a dsl query and execute it
    """
    if not query:
        return ""
    
    query = re.sub(r"[’`‘]", "'", query)
    query = re.sub(r"[”“]", "\"", query)
    query = re.sub(r"\s{2,}", " ", query)
    query = query.strip()

    parts = []
    
    analyses = yajwiz.analyze(fix_xifan(query))
    if analyses:
        parts += fix_analysis_parts(analyses, lang)
    
    if ":" not in query:
        words = query.split(" ")
        analyses = []
        for word in words:
            analyses += yajwiz.analyze(fix_xifan(word))
        
        if analyses:
            parts += fix_analysis_parts(analyses, lang)
    
    included = set()
    ans = []
    for part in parts:
        if part not in included:
            included.add(part)

            ans.append(render_entry(dictionary.entries[part], lang))
    
    ans += dsl_query(query, lang, included)

    return ans

def fix_analysis_parts(analyses: List[yajwiz.analyzer.Analysis], lang: str):
    parts = []
    names = []
    for part in [part for a in analyses for part in a["PARTS"]]:
        names.append(part[:part.index(":")])
        if part not in parts:
            parts.append(part)
        
    parts.sort(key=lambda p: names.index(p[:p.index(":")]))
    return parts

def dsl_query(query: str, lang: str, included: Set[str]):
    parts = [""]
    quote = False
    for i in range(len(query)):
        if not quote and query[i] == " ":
            parts += [""]
            continue
    
        if not quote and query[i] in "()":
            parts += [query[i], ""]
            continue

        if query[i] == "\"":
            quote = not quote
            continue
        
        parts[-1] += query[i]
    
    ans = []
    query_function = parse_or(parts, lang)
    for entry_id, entry in dictionary.entries.items():
        if entry_id not in included and query_function(entry):
            ans.append(render_entry(entry, lang))
    
    return ans

def parse_or(parts: List[str], lang: str):
    a = parse_and(parts, lang)
    while parts and parts[0] in {"OR", "TAI"}:
        parts.pop(0)
        b = parse_and(parts, lang)
        a = create_or(a, b)
    
    return a

def parse_and(parts: List[str], lang: str):
    a = parse_term(parts, lang)
    while parts and parts[0] not in {")", "OR", "TAI"}:
        if parts[0] in {"AND", "JA"}:
            parts.pop(0)
        
        b = parse_term(parts, lang)
        a = create_and(a, b)
    
    return a

def create_or(a, b):
    return lambda *args: (a(*args) or b(*args))

def create_and(a, b):
    return lambda *args: (a(*args) and b(*args))

def parse_term(parts: List[str], lang: str):
    if not parts:
        return lambda *args: True
    
    part = parts.pop(0)
    if part == "(":
        r = parse_or(parts, lang)
        if parts: parts.pop(0) # )
        return r
    
    if ":" in part:
        op = part[:part.index(":")]
        arg = part[part.index(":")+1:]
        if op in QUERY_OPERATORS:
            return lambda entry: QUERY_OPERATORS[op](entry, arg)
        
        else:
            # illegal situation
            return lambda entry: False
    
    else:
        def func(entry: BoqwizEntry):
            if fix_xifan(part) in entry.name:
                return True
            
            if any([tag.startswith(part) for tag in entry.search_tags.get(lang, [])]):
                return True
            
            if part in entry.definition.get(lang, ""):
                return True
            
            return False
        
        return func

def render_entry(entry: BoqwizEntry, language: str) -> dict:
    ans = {
        "name": entry.name,
        "pos": "unknown",
        "tags": [],
    }
    if entry.simple_pos == "v":
        if "is" in entry.tags:
            ans["pos"] = "adjective"
        
        elif "t_c" in entry.tags:
            ans["pos"] = "transitive verb"
        
        elif "t" in entry.tags:
            ans["pos"] = "possibly transitive verb"
        
        elif "i_c" in entry.tags:
            ans["pos"] = "intransitive verb"
        
        elif "i" in entry.tags:
            ans["pos"] = "possibly intransitive verb"
        
        elif "pref" in entry.tags:
            ans["pos"] = "verb prefix"
        
        elif "suff" in entry.tags:
            ans["pos"] = "verb suffix"
        
        else:
            ans["pos"] = "verb"
    
    elif entry.simple_pos == "n":
        if "suff" in entry.tags:
            ans["pos"] = "noun suffix"
        
        else:
            ans["pos"] = "noun"
    
    elif entry.simple_pos == "ques":
        ans["pos"] = "question word"
    
    elif entry.simple_pos == "adv":
        ans["pos"] = "adverb"
    
    elif entry.simple_pos == "conj":
        ans["pos"] = "conjunction"
    
    elif entry.simple_pos == "excl":
        ans["pos"] = "exclamation"
    
    elif entry.simple_pos == "sen":
        ans["pos"] = "sentence"
    
    if "slang" in entry.tags:
        ans["tags"].append("slang")
    
    if "reg" in entry.tags:
        ans["tags"].append("regional")
    
    if "archaic" in entry.tags:
        ans["tags"].append("archaic")
    
    if "hyp" in entry.tags:
        ans["tags"].append("hypothetical")
    
    for i in range(1, 10):
        if str(i) in entry.tags:
            ans["homonym"] = i

    ans["definition"] = fix_links(get_unless_translated(entry.definition, language))
    if entry.notes:
        ans["notes"] = fix_links(get_unless_translated(entry.notes, language))
    
    if entry.examples:
        ans["examples"] = fix_links(get_unless_translated(entry.examples, language))
    
    if entry.simple_pos == "n":
        if "inhps" in entry.tags and entry.components:
            ans["see"] = fix_links(entry.components)
        
        elif "suff" not in entry.tags and "inhpl" not in entry.tags:
            if "body" in entry.tags:
                ans["inflections"] = "-Du'"
            
            elif "being" in entry.tags:
                ans["inflections"] = "-pu', -mey"
            
    if entry.components:
        ans["components"] = fix_links(entry.components)

    for field in ["components", "synonyms", "antonyms", "see_also", "source"]:
        if getattr(entry, field):
            ans[field] = fix_links(getattr(entry, field))
    
    return ans

def get_unless_translated(d, l):
    if l not in d or not d[l]:
        return d.get("en", "")
    
    elif "AUTOTRANSLATED" in d[l]:
        return d["en"]
    
    else:
        return d[l]

def fix_links(text: str) -> str:
    ans = ""
    while "{" in text:
        i = text.index("{")
        ans += text[:i]
        text = text[i+1:]
        i = text.index("}")
        link = text[:i]
        ans += fix_link(link)
        text = text[i+1:]
    
    ans += text
    return ans.replace("\n", "<br>")

def fix_link(link: str) -> str:
    if link.endswith(":nolink"):
        return "<b>" + link[:link.index(":")] + "</b>"
    
    elif link.endswith(":src"):
        return "<i>" + link[:link.index(":")] + "</i>"
    
    elif link.count(":url:") == 1:
        [text, addr] = link.split(":url:")
        return f"<a target=_blank href=\"{addr}\">{text}</a>"
    
    elif "@@" in link:
        text = link[:link.index("@@")]
        return f"<a href=\"?q={text.replace(' ', '+')}\">{text}</a>"
    
    elif ":" in link:
        text = link[:link.index(":")]
        return f"<a href=\"?q={text.replace(' ', '+')}\">{text}</a>"
    
    else:
        text = link
        return f"<a href=\"?q={text.replace(' ', '+')}\">{text}</a>"

def fix_xifan(query: str) -> str:
    query = re.sub(r"i", "I", query)
    query = re.sub(r"d", "D", query)
    query = re.sub(r"s", "S", query)
    query = re.sub(r"([^cgl]|[^t]l|^)h", r"\1H", query)
    query = re.sub(r"x", "tlh", query)
    query = re.sub(r"f", "ng", query)
    query = re.sub(r"c(?!h)", "ch", query)
    query = re.sub(r"(?<!n)g(?!h)", "gh", query)
    return query

@routes.get("/api/analyze")
async def analyze(request):
    if "word" not in request.query:
        raise web.HTTPBadRequest()
    word = request.query["word"]
    return web.json_response(yajwiz.analyze(word))

@routes.post("/api/grammar_check")
async def grammar_check(request):
    text = await request.text()
    errors = yajwiz.get_errors(text)
    return web.json_response(errors)

routes.static('/', "static/")

app = web.Application()
aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('templates/'))
app.add_routes(routes)
web.run_app(app)
