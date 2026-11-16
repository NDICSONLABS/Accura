import os
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from app.core.i18n import get_locale, get_translator


class I18nJinja2Templates(Jinja2Templates):
    def TemplateResponse(self, *args, **kwargs):
        # 1. Extract kwargs
        request = kwargs.pop("request", None)
        name = kwargs.pop("name", None)
        context = kwargs.pop("context", None)

        # 2. Handle positional arguments (bulletproof detection)
        if len(args) > 0:
            if isinstance(args[0], Request):
                # Modern signature: TemplateResponse(request, name, context)
                request = args[0]
                if len(args) > 1: name = args[1]
                if len(args) > 2: context = args[2]
            elif isinstance(args[0], str):
                # Old signature: TemplateResponse(name, context)
                name = args[0]
                if len(args) > 1 and isinstance(args[1], dict):
                    context = args[1]
            elif isinstance(args[0], dict):
                # Very old signature: TemplateResponse(context, name)
                context = args[0]
                if len(args) > 1 and isinstance(args[1], str):
                    name = args[1]

        # 3. Extract request from context dict if it was passed the old way
        if not request and isinstance(context, dict) and "request" in context:
            request = context["request"]

        if context is None:
            context = {}

        # 4. Inject i18n and enforce modern Starlette signature
        if request:
            context["request"] = request
            try:
                locale = get_locale(request)
                translator = get_translator(locale)
                context["_"] = translator.gettext
                context["locale"] = locale
            except Exception:
                pass  # Fail gracefully if i18n breaks

            # ALWAYS call parent with modern signature: (request, name, context)
            return super().TemplateResponse(request, name, context, **kwargs)
        else:
            # Fallback (should rarely happen in FastAPI)
            return super().TemplateResponse(name, context, **kwargs)


templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = I18nJinja2Templates(directory=templates_dir)