*** Settings ***
Documentation    Minimal smoke suite for the local Docker stack.
Library          ${CURDIR}/../TestKeywords/http_keywords.py
Suite Setup      Open Smoke Sessions
Test Tags        smoke    allure.label.epic:System Tests    allure.label.feature:Smoke

*** Test Cases ***
Session Health Endpoint Responds
    [Tags]    session    health    allure.label.story:Session service exposes health probes
    Internal Endpoint Should Return Json Status    session    /healthz    ok

Session Readiness Endpoint Responds
    [Tags]    session    readiness    allure.label.story:Session service verifies readiness dependencies
    Internal Endpoint Should Return Json Status    session    /readyz    ready

Wallet Health Endpoint Responds
    [Tags]    wallet    health    allure.label.story:Wallet service exposes health probes
    Internal Endpoint Should Return Status    wallet    /healthz    200

Stock Health Endpoint Responds
    [Tags]    stock    health    allure.label.story:Stock service exposes health probes
    Internal Endpoint Should Return Status    stock    /healthz    200

Legacy UI Login Route Responds Through Traefik
    [Tags]    wallet-ui    traefik    allure.label.story:Traefik routes legacy UI login
    Traefik Route Should Return Status    wallet.localhost    /login    200

Next UI Login Route Responds Through Traefik
    [Tags]    next-ui    traefik    allure.label.story:Traefik routes next-ui login
    Traefik Route Should Return Status    next.localhost    /login    200
