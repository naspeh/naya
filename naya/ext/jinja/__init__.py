import mimetypes

from jinja2 import (
    Environment, TemplateNotFound,
    PrefixLoader as PrefixLoaderBase, FileSystemLoader, ChoiceLoader
)

from naya.helpers import register


class JinjaMixin(object):
    @register('init')
    def jinja_init(self):
        self.jinja = False
        jinja_loaders = {}

        shared = self.conf['jinja:shared']
        endpoint = self.conf['jinja:endpoint']
        url_prefix = self.conf['jinja:url_prefix']

        for name, module in self.modules.items():
            module, prefix = module
            if not module.theme_path:
                continue

            prefix = prefix and '/%s' % prefix or prefix
            loader = FileSystemLoader(
                module.theme_path
            )

            jinja_loaders.setdefault(prefix, [])
            jinja_loaders[prefix].append(FileSystemLoader(
                module.theme_path
            ))
            if shared:
                prefix = prefix.lstrip('/')
                prefix = '%s%s' % (url_prefix, prefix)
                self.share(module, prefix, endpoint)

        if jinja_loaders:
            for prefix, loader in jinja_loaders.items():
                if isinstance(loader, list):
                    jinja_loaders[prefix] = ChoiceLoader(loader)

            self.jinja = Environment(loader=PrefixLoader(jinja_loaders))
            self.jinja.filters.update(self.conf['jinja:filters'])
            if shared:
                self.share(self, url_prefix, endpoint)
                self.dispatch = SharedJinjaMiddleware(
                    self.dispatch, self, url_prefix
                )

    @register('default_prefs')
    def jinja_prefs(self):
        return {
            'jinja': {
                'shared': True,
                'endpoint': 'jinja',
                'url_prefix': '/t/',
                'path_ends': [],
                'filters': {},
            }
        }


class PrefixLoader(PrefixLoaderBase):
    def get_source(self, environment, template):
        for prefix, loader in self.mapping.items():
            path = template
            if path.startswith(prefix):
                path = template[len(prefix):]
            path = path.lstrip('/')
            try:
                return loader.get_source(environment, path)
            except TemplateNotFound:
                pass
        raise TemplateNotFound(template)


class SharedJinjaMiddleware(object):
    def __init__(self, dispatch, app, prefix, context={}):
        self.dispatch = dispatch
        self.app = app
        self.prefix = prefix
        self.context = context

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '/')
        template = None
        if path.startswith(self.prefix):
            path = path[len(self.prefix):]
            path = '/%s' % path.strip('/')
            path = path.rstrip('/')

            path_ends = self.app.conf['jinja:path_ends']
            paths = path_ends and [path + item for item in path_ends] or []
            paths = [path] + paths

            try:
                template = self.app.jinja.select_template(paths)
            except TemplateNotFound:
                template = None

        if not template:
            return self.dispatch(environ, start_response)

        path = template.name

        guessed_type = mimetypes.guess_type(path)
        mime_type = guessed_type[0] or 'text/plain'

        context = {'app': self.app, 'template': path.lstrip('/')}
        context.update(self.context)

        template = template.render(context)

        response = self.app.response_class(template, mimetype=mime_type)
        return response(environ, start_response)