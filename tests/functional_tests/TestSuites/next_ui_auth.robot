*** Settings ***
Documentation    Browser-level functional checks for next-ui public and auth routes.
Library          Browser    timeout=15s    enable_playwright_debug=${False}
Library          ${CURDIR}/../TestKeywords/browser_keywords.py
Library          ${CURDIR}/../TestKeywords/allure_helper.py    WITH NAME    AllureHelper
Suite Setup      Open Next Ui Browser
Suite Teardown   Close Browser And Keep Failure Artifacts
Test Tags        functional    next-ui    allure.label.epic:System Tests    allure.label.feature:Functional    allure.label.tag:functional    allure.label.tag:next-ui    allure.label.severity:normal

*** Variables ***
${BASE_URL}     http://traefik
${HEADLESS}     True

*** Test Cases ***
Public Home Shows Auth Entry Points
    [Tags]    smoke    allure.label.story:Public home exposes authentication entry points    allure.label.severity:normal    allure.label.tag:smoke
    Go To Next Ui Path    /home
    Capture Test Screenshot
    Page Should Have Text    Zyskaj kontrolę
    Page Should Have Text    Zarejestruj się
    Page Should Have Text    Zaloguj się

Login Page Exposes Stable Authentication Form
    [Tags]    auth    allure.label.story:Login page exposes stable authentication form    allure.label.severity:critical    allure.label.tag:auth
    Go To Next Ui Path    /login
    Capture Test Screenshot
    Page Should Have Text    FinancialManager
    Get Element    input[name="email"]
    Get Element    input[name="password"]
    Get Element    role=button[name=/zaloguj/i]

Register Page Exposes Stable Registration Form
    [Tags]    auth    allure.label.story:Register page exposes stable registration form    allure.label.severity:critical    allure.label.tag:auth
    Go To Next Ui Path    /register
    Capture Test Screenshot
    Page Should Have Text    Rejestracja
    Get Element    input[name="first_name"]
    Get Element    input[name="last_name"]
    Get Element    input[name="username"]
    Get Element    input[name="email"]
    Get Element    input[name="password"]

Protected Wallet Route Returns Auth Error For Anonymous User
    [Tags]    auth    critical    allure.label.story:Protected wallet route rejects anonymous users    allure.label.severity:blocker    allure.label.tag:auth    allure.label.tag:security
    Go To Next Ui Path    /wallet
    Capture Test Screenshot
    Page Should Have Text    Please login
