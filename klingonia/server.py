from collections import defaultdict
from aiohttp import web
import aiohttp_jinja2
import jinja2
import yajwiz

import logging

from . import locales, dictionary

logging.basicConfig(level=logging.INFO)

routes = web.RouteTableDef()

@routes.get('/')
@routes.get('/index/{lang}')
@routes.get('/index/{lang}/')
@aiohttp_jinja2.template("index.jinja2")
async def get_index(request):
    lang = request.match_info.get("lang", "en")
    return {"lang": locales.locale_map[lang], "path": "/index"}

@routes.get('/proofread')
@routes.get('/proofread/')
@routes.get('/proofread/{lang}')
@routes.get('/proofread/{lang}/')
@aiohttp_jinja2.template("proofreader.jinja2")
async def get_proofread(request):
    lang = request.match_info.get("lang", "en")
    bare = request.query.get("bare", "") != ""
    return {"lang": locales.locale_map[lang], "path": "/proofread", "input": "", "result": "", "bare": bare}

@routes.post("/proofread")
@routes.post("/proofread/{lang}")
@aiohttp_jinja2.template("proofreader.jinja2")
async def post_proofread(request):
    lang = request.match_info.get("lang", "en")
    query = await request.post()
    if "text" not in query:
        raise web.HTTPBadRequest()
    
    n_errors, render = check_and_render(query["text"])
    bare = request.query.get("bare", "") != ""
    return {
        "lang": locales.locale_map[lang],
        "path": "/proofread",
        "input": query["text"],
        "result": render,
        "no_errors": n_errors == 0,
        "bare": bare,
    }

def check_and_render(text: str):
    errors = yajwiz.get_errors(text)
    errors.sort(key=lambda e: e.location)
    error_dict = defaultdict(list)
    for error in errors:
        error_dict[error.location].append(error)
    
    ans = ""
    close_dict = defaultdict(lambda: 0)
    for i in range(len(text)):
        ans += "</span>" * close_dict[i]
        if i in error_dict:
            for error in sorted(error_dict[i], key=lambda e: e.end_location):
                ans += f'<span class=error title="{error.message}">'
                close_dict[error.end_location] += 1
            
        ans += text[i]
    
    return len(errors), ans

@routes.get('/dictionary')
@routes.get('/dictionary/')
@routes.get('/dictionary/{lang}')
@routes.get('/dictionary/{lang}/')
@aiohttp_jinja2.template("dictionary.jinja2")
async def get_dictionary(request: web.Request):
    lang = request.match_info.get("lang", "en")
    query = request.query.get("q", "")
    accent = request.query.get("accent", "") != ""
    bare = request.query.get("bare", "") != ""
    return {
        "lang": locales.locale_map[lang],
        "path": "/dictionary",
        "input": query,
        "result": dictionary.dictionary_query(query, lang, accent),
        "boqwiz_version": dictionary.dictionary.version,
        "bare": bare
    }

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

routes.static('/static/', "static/")

app = web.Application()
aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('templates/'))
app.add_routes(routes)
web.run_app(app)
