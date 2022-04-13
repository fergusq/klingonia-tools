from collections import defaultdict
from klingonia.proofread import check_and_render
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

@routes.get('/dictionary')
@routes.get('/dictionary/')
@routes.get('/dictionary/{lang}')
@routes.get('/dictionary/{lang}/')
@aiohttp_jinja2.template("dictionary.jinja2")
async def get_dictionary(request: web.Request):
    lang = request.match_info.get("lang", "en")
    query = request.query.get("q", "")
    bare = request.query.get("bare", "") != ""
    return {
        "lang": locales.locale_map[lang],
        "path": "/dictionary",
        "input": query,
        "result": dictionary.dictionary_query(query, lang),
        "boqwiz_version": dictionary.dictionary.version,
        "bare": bare
    }

@routes.get("/api/analyze")
async def api_analyze(request):
    if "word" not in request.query:
        raise web.HTTPBadRequest()
    word = request.query["word"]
    return web.json_response(yajwiz.analyze(word))

@routes.post("/api/grammar_check")
async def api_grammar_check(request):
    text = await request.text()
    errors = yajwiz.get_errors(text)
    return web.json_response(errors)

@routes.post("/api/proofread")
async def api_proofread(request):
    lang = request.match_info.get("lang", "en")
    text = await request.text()
    n_errors, render = check_and_render(text)
    return web.json_response({
        "n_errors": n_errors,
        "render": render,
    })

routes.static('/static/', "static/")

app = web.Application()
aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('templates/'))
app.add_routes(routes)
web.run_app(app)
