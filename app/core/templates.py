import os
import json
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from app.core.i18n import get_locale, get_translator


class I18nJinja2Templates(Jinja2Templates):
    """
    Custom Jinja2Templates wrapper that:
      1. Handles both legacy (name, context) and modern (request, name, context) signatures.
      2. Injects the i18n `_` translation function and current `locale` into every template.
      3. Auto-injects a normalized `settings` dict into every template so feature-flag
         driven navigation/UI is consistent regardless of which router rendered the page.
      4. Registers a `tojson` filter for safely embedding Python objects as JSON.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # `tojson` is NOT available in plain Starlette/Jinja2 by default — register it.
        self.env.filters["tojson"] = self._tojson

    @staticmethod
    def _tojson(value):
        # Return a plain string; Jinja2 autoescape will HTML-escape it appropriately
        # for the surrounding context (safe inside HTML attributes such as x-data).
        return json.dumps(value, default=str, ensure_ascii=False)

    def TemplateResponse(self, *args, **kwargs):
        # --- Argument normalization (support old & new Starlette signatures) ---
        request = kwargs.pop("request", None)
        name = kwargs.pop("name", None)
        context = kwargs.pop("context", None)

        if len(args) > 0:
            if isinstance(args[0], Request):
                request = args[0]
                if len(args) > 1:
                    name = args[1]
                if len(args) > 2:
                    context = args[2]
            elif isinstance(args[0], str):
                name = args[0]
                if len(args) > 1 and isinstance(args[1], dict):
                    context = args[1]
            elif isinstance(args[0], dict):
                context = args[0]
                if len(args) > 1 and isinstance(args[1], str):
                    name = args[1]

        if not request and isinstance(context, dict) and "request" in context:
            request = context["request"]

        if context is None:
            context = {}

        if request:
            context["request"] = request

            # --- i18n injection ---
            try:
                locale = get_locale(request)
                translator = get_translator(locale)
                context["_"] = translator.gettext
                context["locale"] = locale
            except Exception:
                pass  # Fail gracefully if i18n is misconfigured

            # --- Consistent settings injection (normalized dict) ---
            context["settings"] = self._resolve_settings(context.get("settings"))

            # Always call parent with the modern signature: (request, name, context)
            return super().TemplateResponse(request, name, context, **kwargs)
        else:
            return super().TemplateResponse(name, context, **kwargs)

    @staticmethod
    def _resolve_settings(raw):
        """
        Normalize settings into a plain, JSON-safe dict so every template can rely on
        a consistent structure, whether a router passed an ORM object, a dict, or nothing.
        """
        # Lazy imports to avoid circular dependencies at module load time.
        from app.services.settings_service import settings_to_dict
        from app.core.database import SessionLocal
        from app.models.settings import OrganizationSetting

        try:
            if raw is not None:
                return settings_to_dict(raw)

            db = SessionLocal()
            try:
                settings = db.query(OrganizationSetting).first()
                return settings_to_dict(settings)
            finally:
                db.close()
        except Exception:
            return settings_to_dict(None)


templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = I18nJinja2Templates(directory=templates_dir)