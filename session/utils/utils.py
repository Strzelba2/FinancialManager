from django.http import JsonResponse
from django.template.response import TemplateResponse


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def formatted_response(request, data, template_name=None, status=200):
    """
    Return an appropriate response based on the request's accepted format.

    Args:
        request: The request object.
        data: The data to include in the response.
        template_name: The name of the template to render (for HTML responses).
        status: The HTTP status code for the response.

    Returns:
        Response: A Response object.
    """
    if template_name and request.headers.get("Accept", "").startswith("text/html"):
        response = TemplateResponse(request, template_name, data, status=status)
        response.render()
    else:
        response = JsonResponse(data, status=status)
    
    return response
