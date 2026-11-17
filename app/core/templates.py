import os
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.core.i18n import get_locale, get_translator, translate_message


class I18nJinja2Templates(Jinja2Templates):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.env.filters["tojson"] = self._tojson
        self.env.filters["fmoney"] = self._fmoney

    @staticmethod
    def _tojson(value):
        return json.dumps(value, default=str, ensure_ascii=False)

    @staticmethod
    def _fmoney(amount, currency: str = "XAF") -> str:
        if amount is None:
            amount = Decimal("0")
        if not isinstance(amount, Decimal):
            try:
                amount = Decimal(str(amount))
            except (InvalidOperation, ValueError):
                amount = Decimal("0")

        if currency == "XAF":
            rounded = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return f"{rounded:,.0f}"

        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{rounded:,.2f}"

    def TemplateResponse(self, *args, **kwargs):
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
            from app.core.config import settings as app_settings
            # An explicitly supplied token (e.g. freshly minted on the login page)
            # must win over the incoming cookie, otherwise form and cookie diverge.
            if not context.get("csrf_token"):
                context["csrf_token"] = request.cookies.get(app_settings.CSRF_COOKIE_NAME, "")

            context["request"] = request

            locale = get_locale(request)
            translator = get_translator(locale)

            context["_"] = translator.gettext
            context["locale"] = locale
            context["tmsg"] = lambda msg: translate_message(request, msg)

            context["settings"] = self._resolve_settings(context.get("settings"))

            return super().TemplateResponse(request, name, context, **kwargs)

        return super().TemplateResponse(name, context, **kwargs)

    @staticmethod
    def _resolve_settings(raw):
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