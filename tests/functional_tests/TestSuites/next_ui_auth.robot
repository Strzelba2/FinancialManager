*** Settings ***
Documentation    Browser-level functional checks for next-ui public and auth routes.
Library          Browser    timeout=15s    enable_playwright_debug=${False}
Library          ${CURDIR}/../TestKeywords/browser_keywords.py
Library          ${CURDIR}/../TestKeywords/auth_keywords.py
Library          ${CURDIR}/../TestKeywords/allure_helper.py    WITH NAME    AllureHelper
Suite Setup      Open Next Ui Browser
Suite Teardown   Close Browser And Keep Failure Artifacts
Test Tags        functional    next-ui    allure.label.epic:System Tests    allure.label.feature:Functional    allure.label.tag:functional    allure.label.tag:next-ui    allure.label.severity:normal

*** Variables ***
${BASE_URL}     http://next.localhost
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
    Page Should Have Text    401 - Access Denied
    Page Should Have Text    User does not have permission to this site. Please login.
    Page Should Have Text    Go to Login

Duplicate Favorite List Shows Conflict Message
    [Tags]    wallet    favorites    critical    allure.label.story:Duplicate favorite list names are rejected in Next UI    allure.label.severity:critical    allure.label.tag:wallet    allure.label.tag:favorites    allure.label.tag:financial-data
    ${user}=    Create Active Functional User    favui
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/wallet')
    Go To Next Ui Path    /user/favorites
    Page Should Have Text    Ulubione & Alerty
    Click    role=button[name=/Utwórz pierwszą listę/i]
    Fill Text    role=textbox[name="Nazwa *"]    My watchlist
    Click    role=button[name=/^Utwórz$/i]
    Page Should Have Text    My watchlist
    Click    role=button[name=/Dodaj listę/i]
    Fill Text    role=textbox[name="Nazwa *"]    My watchlist
    Click    role=button[name=/^Utwórz$/i]
    Page Should Have Text    Favorite list with this name already exists for this user.
    Capture Test Screenshot
