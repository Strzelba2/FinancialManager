import re


def is_valid_email(email):
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return "Nie poprawny format email"


def is_valid_password(password):
    if len(password) < 12:
        return "Hasło musi mieć co najmniej 12 znaków."
    if not re.search(r'[A-Za-z]', password):
        return "Hasło musi zawierać przynajmniej jedną literę."
    if not re.search(r"[0-9]", password):
        return "Hasło musi zawierać przynajmniej jedną cyfrę."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return "Hasło musi zawierać przynajmnie jeden specjalny znak"
