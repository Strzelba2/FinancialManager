from django.http import JsonResponse
from django.template.response import TemplateResponse
import json
import ast
from ipaddress import ip_address, ip_network
from typing import Union
import logging

logger = logging.getLogger("session-auth")


def get_client_ip(request):
    original_ip = request.META.get("HTTP_X_ORIGINAL_CLIENT_IP", "").strip()
    if original_ip:
        return original_ip

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    x_real_ip = request.META.get("HTTP_X_REAL_IP", "")
    if x_real_ip:
        return x_real_ip.strip()

    return request.META.get("REMOTE_ADDR", "").strip()


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
    Parse allowed IPs / CIDRs into a normalized flat list of strings.

    Examples:
        '["localhost", "192.168.0.1", "10.20.0.0/16"]'
        ["localhost", "192.168.0.1", "10.20.0.0/16"]
    """
    logger.info(f"Raw input: {value} ({type(value).__name__})")

    tokens: list[str] = []

    if isinstance(value, (list, tuple, set)):
        tokens = [str(x).strip() for x in value if str(x).strip()]

    elif isinstance(value, str):
        raw = value.strip()

        if not raw:
            return []

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = ast.literal_eval(raw)

        if isinstance(parsed, (list, tuple, set)):
            tokens = [str(x).strip() for x in parsed if str(x).strip()]
        else:
            tokens = [str(parsed).strip()]

    normalized: list[str] = []
    for token in tokens:
        if token.lower() == "localhost":
            token = "127.0.0.1"
        normalized.append(token)

    logger.info(f"Final allowed entries: {normalized}")
    return normalized


def is_ip_allowed(client_ip: str, allowed_entries: list[str]) -> bool:
    """
    Check whether client_ip matches any exact IP or CIDR entry.
    """
    try:
        ip = ip_address(client_ip)
    except ValueError:
        logger.error(f"Invalid client IP: {client_ip}")
        return False

    for entry in allowed_entries:
        try:
            if "/" in entry:
                if ip in ip_network(entry, strict=False):
                    logger.info(f"IP {client_ip} matched subnet {entry}")
                    return True
            else:
                if ip == ip_address(entry):
                    logger.info(f"IP {client_ip} matched exact IP {entry}")
                    return True
        except ValueError:
            logger.warning(f"Skipping invalid allowed entry: {entry}")

    logger.warning(f"IP {client_ip} is not allowed")
    return False