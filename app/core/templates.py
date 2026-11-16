import os
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from app.core.i18n import get_locale, get_translator


class I18nJinja2Templates(Jinja2Templates):
    def TemplateResponse(
            self,
            request: Request,
            name: str,
            context: dict | None = None,
            **kwargs
    ):
        if context is None:
            context = {}

        # Ensure request is always in the context
        context["request"] = request

        locale = get_locale(request)
        translator = get_translator(locale)

        # Inject translation function and current locale into template context
        context["_"] = translator.gettext
        context["locale"] = locale

        # Call the parent class with the correct modern signature
        return super().TemplateResponse(request, name, context, **kwargs)


templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = I18nJinja2Templates(directory=templates_dir)