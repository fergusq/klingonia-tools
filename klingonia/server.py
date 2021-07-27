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
    return {"lang": locales.locale_map[lang], "path": "/dictionary", "input": query, "result": dictionary.dictionary_query(query, lang), "boqwiz_version": dictionary.dictionary.version}

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
