# Marca el paquete
from fastapi.templating import Jinja2Templates
import inspect

_original_template_response = Jinja2Templates.TemplateResponse

def _compat_template_response(self, *args, **kwargs):
    sig = inspect.signature(_original_template_response)
    if "request" in sig.parameters:
        name = kwargs.get('name') or (args[0] if len(args) > 0 else None)
        context = kwargs.get('context') or (args[1] if len(args) > 1 else {})
        request = context.get('request')
        
        new_args = [request, name, context]
        if len(args) > 2:
            new_args.extend(args[2:])
            
        new_kwargs = {k: v for k, v in kwargs.items() if k not in ['name', 'context']}
        return _original_template_response(self, *new_args, **new_kwargs)
    else:
        return _original_template_response(self, *args, **kwargs)

Jinja2Templates.TemplateResponse = _compat_template_response
