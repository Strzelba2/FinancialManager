from django.http import JsonResponse
from django.template.response import TemplateResponse
import json
from typing import Union
import logging

logger = logging.getLogger("session-auth")


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


def parse_allowed(value: Union[str, list[str], tuple, set]) -> list[str]:
    """
    Parses a list of allowed IPs or CIDR-like entries into a flat list of IP strings.
    
    Args:
        value (Union[str, list, tuple, set]): 
            A JSON string or list-like structure containing allowed IPs/subnets.
            Examples:
                '["localhost", "192.168.0.1", "10.0.0.0/3"]'
                ['localhost', '192.168.0.1', '10.0.0.0/3']

    Returns:
        list[str]: A flat list of allowed IP strings.
    """
    logger.info(f"Raw input: {value} ({type(value).__name__})")
    
    tokens: list[str] = []
    if isinstance(value, (list, tuple, set)):
        tokens = [str(x) for x in value]
    elif isinstance(value, str):
        tokens = json.loads(value)

    nets: list[str] = []
    for t in tokens:
        t = str(t).strip().split("/")  
        if not t:
            continue
        
        if t[0].lower() == "localhost":
            t = "127.0.0.1"

        if len(t) == 2:
            
            for i in range(int(t[1])):
                nets.append(f"{t[0][:-1]}{i}")
        else:
            nets.append(t)
            
    logger.info(f"Final allowed IPs: {nets}")   
    return nets
