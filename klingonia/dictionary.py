import logging
import re
import sys
from typing import Dict, Callable, Any, List, Set

import yajwiz
from yajwiz import BoqwizEntry

from . import locales

logger = logging.getLogger("dictionary")

dictionary = yajwiz.load_dictionary()

QUERY_OPERATORS: Dict[str, Callable[[BoqwizEntry, str], Any]] = {
    "tlh": lambda entry, arg: re.search(fix_xifan(arg), entry.name),
    "notes": lambda entry, arg: re.search(arg, entry.notes.get("en", ""), re.IGNORECASE),
    "ex": lambda entry, arg: re.search(arg, entry.examples.get("en", "")),
    "pos": lambda entry, arg: set(arg.split(",")) <= ({entry.simple_pos} | entry.tags),
    "antonym": lambda entry, arg: re.search(fix_xifan(arg), entry.antonyms or ""),
    "synonym": lambda entry, arg: re.search(fix_xifan(arg), entry.synonyms or ""),
    "components": lambda entry, arg: re.search(fix_xifan(arg), entry.components or ""),
    "see": lambda entry, arg: re.search(fix_xifan(arg), entry.see_also or ""),
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
        try:
            f = query_function(entry)
        
        except:
            logger.exception("Error during executing query", exc_info=sys.exc_info())
            f = False
        
        if entry_id not in included and f:
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
            
            if any([tag.lower().startswith(part.lower()) for tag in entry.search_tags.get(lang, [])]):
                return True
            
            if part.lower() in entry.definition.get(lang, "").lower():
                return True
            
            return False
        
        return func

def get_wiki_name(name: str) -> str:
    name = name.replace(" ", "")
    ans = ""
    for letter in yajwiz.split_to_letters(name):
        if letter == "q":
            ans += "k"
        
        elif letter == "'":
            ans += "-"
        
        else:
            ans += letter
    
    return ans.capitalize()

def render_entry(entry: BoqwizEntry, language: str) -> dict:
    ans = {
        "name": entry.name,
        "url_name": entry.name.replace(" ", "+"),
        "wiki_name": get_wiki_name(entry.name),
        "pos": "unknown",
        "simple_pos": "affix" if "-" in entry.name else entry.simple_pos,
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

    if language != "en":
        ans["english"] = fix_links(entry.definition["en"])

    if entry.notes:
        ans["notes"] = fix_links(get_unless_translated(entry.notes, language))
    
    if entry.examples:
        ans["examples"] = fix_links(get_unless_translated(entry.examples, language))
            
    if entry.components:
        ans["components"] = fix_links(entry.components)
    
    if entry.simple_pos == "n":
        if "inhps" in entry.tags and entry.components:
            ans["inflections"] = locales.locale_map[language]["plural"] + ": " + fix_links(entry.components)
            del ans["components"]

        elif "inhpl" in entry.tags and entry.components:
            ans["inflections"] = locales.locale_map[language]["singular"] + ": " + fix_links(entry.components)
            del ans["components"]
        
        elif "suff" not in entry.tags and "inhpl" not in entry.tags:
            if "body" in entry.tags:
                ans["inflections"] = "-Du'"
            
            elif "being" in entry.tags:
                ans["inflections"] = "-pu', -mey"

    for field in ["synonyms", "antonyms", "see_also", "source", "hidden_notes"]:
        if getattr(entry, field):
            ans[field] = fix_links(getattr(entry, field))
    
    return ans

def get_unless_translated(d, l):
    if l not in d or not d[l]:
        return d.get("en", "")
    
    elif "AUTOTRANSLATED" in d[l] or d[l] == "TRANSLATE":
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
    parts1 = link.split("@@")
    parts2 = parts1[0].split(":")
    link_text = parts2[0]
    link_text2 = link_text
    link_type = parts2[1] if len(parts2) > 1 else ""
    tags = parts2[2].split(",") if len(parts2) > 2 else []
    
    if "nolink" in tags:
        style = "affix" if "-" in link_text else link_type if link_type else "sen"
        return f"<b class=\"pos-{style}\" okrand>" + link_text2 + "</b>"
    
    elif link_type == "src":
        return "<i>" + link_text + "</i>"
    
    elif link_type == "url":
        addr = parts2[2]
        return f"<a target=_blank href=\"{addr}\">{link_text}</a>"
    
    elif len(parts1) == 2:
        style = link_type if link_type else "sen"
        return f"<a href=\"?q={link_text.replace(' ', '+')}\" class=\"pos-{style}\" okrand>{link_text2}</a>"
    
    else:
        hyp = "<sup>?</sup>" if "hyp" in tags else ""
        hom = ""
        hom_pos = ""
        for i in range(1, 10):
            if str(i) in tags:
                hom = f"<sup>{i}</sup>"
                hom_pos = f"+pos:{i}"
                break
            
            elif f"{i}h" in tags:
                hom_pos = f"+pos:{i}"
                break

        pos = "+pos:"+link_type if link_type and link_type != "sen" else ""
        style = "affix" if "-" in link_text else link_type if link_type else "sen"
        return f"<a href=\"?q=tlh:&quot;^{link_text.replace(' ', '+')}$&quot;{pos}{hom_pos}\" class=\"pos-{style}\">{hyp}<span okrand>{link_text2}</span>{hom}</a>"

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