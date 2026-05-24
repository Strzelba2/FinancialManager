*** Settings ***
Documentation    Browser-level functional checks for next-ui public and auth routes.
Library          Browser    timeout=15s    enable_playwright_debug=${False}
Library          ${CURDIR}/../TestKeywords/browser_keywords.py
Library          ${CURDIR}/../TestKeywords/auth_keywords.py
Library          ${CURDIR}/../TestKeywords/allure_helper.py    WITH NAME    AllureHelper
Suite Setup      Open Next Ui Browser
Suite Teardown   Close Browser And Keep Failure Artifacts
Test Setup       Reset Functional Auth Rate Limits
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

Protected Dashboard Routes Reject Anonymous User
    [Tags]    auth    security    critical    allure.label.story:Protected dashboard routes reject anonymous users    allure.label.severity:blocker    allure.label.tag:auth    allure.label.tag:security
    Go To Next Ui Path    /transactions
    Page Should Have Text    401 - Access Denied
    Page Should Have Text    User does not have permission to this site. Please login.
    Go To Next Ui Path    /wallet-manager
    Page Should Have Text    401 - Access Denied
    Page Should Have Text    User does not have permission to this site. Please login.
    Go To Next Ui Path    /brokerage/holdings
    Page Should Have Text    401 - Access Denied
    Page Should Have Text    User does not have permission to this site. Please login.
    Capture Test Screenshot

Active User Can Login And Reach Wallet
    [Tags]    auth    critical    allure.label.story:Active user can login through Next UI    allure.label.severity:blocker    allure.label.tag:auth
    ${user}=    Create Active Functional User    loginok
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/wallet')
    Capture Test Screenshot

Cross Site Post To Protected Wallet Api Is Blocked
    [Tags]    auth    security    csrf    critical    allure.label.story:Cross-site POST cannot reach protected Next wallet API with browser cookies    allure.label.severity:blocker    allure.label.tag:auth    allure.label.tag:security    allure.label.tag:csrf
    ${user}=    Create Active Functional User    csrfapi
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/wallet')
    Cross Site Form Post To Next Ui Path Should Be Blocked    /api/wallet/transactions
    Capture Test Screenshot
    Go To Next Ui Path    /wallet
    Page Should Not Have Text    401 - Access Denied

Logout Page Requires Explicit Confirmation Before Ending Session
    [Tags]    auth    logout    security    csrf    critical    allure.label.story:Logout is a POST confirmation flow instead of a GET side effect    allure.label.severity:blocker    allure.label.tag:auth    allure.label.tag:security    allure.label.tag:logout    allure.label.tag:csrf
    ${user}=    Create Active Functional User    logoutui
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/wallet')
    Go To Next Ui Path    /logout
    Page Should Have Text    Wylogować z konta?
    Go To Next Ui Path    /wallet
    Page Should Not Have Text    401 - Access Denied
    Go To Next Ui Path    /logout
    Click    role=button[name=/wyloguj się/i]
    Wait For Function    () => window.location.pathname.includes('/login')
    Go To Next Ui Path    /wallet
    Page Should Have Text    401 - Access Denied
    Capture Test Screenshot

User Can Enable 2FA And Complete Next Login Challenge
    [Tags]    auth    2fa    security    critical    allure.label.story:User enables 2FA in profile and completes Next UI login challenge    allure.label.severity:blocker    allure.label.tag:auth    allure.label.tag:security    allure.label.tag:2fa
    ${user}=    Create Active Functional User    twofaui
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/wallet')
    Go To Next Ui Path    /settings/profile
    Page Should Have Text    Uwierzytelnianie dwuskładnikowe
    Click    role=button[name=/Wygeneruj kod QR/i]
    Get Element    img[alt="Kod QR 2FA"]
    ${code}=    Generate Functional User Totp Code    ${user}
    Fill Text    input[name="token"]    ${code}
    Click    role=button[name=/Włącz 2FA/i]
    Page Should Have Text    Status: aktywne
    Go To Next Ui Path    /logout
    Click    role=button[name=/wyloguj się/i]
    Wait For Function    () => window.location.pathname.includes('/login')
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/two-factor')
    ${login_code}=    Generate Functional User Totp Code    ${user}
    Fill Text    input[name="token"]    ${login_code}
    Click    role=button[name=/Potwierdź kod/i]
    Wait For Function    () => window.location.pathname.includes('/wallet')
    Capture Test Screenshot

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

Invalid Password Shows Login Error
    [Tags]    auth    negative    security    critical    allure.label.story:Invalid password is rejected in Next UI login    allure.label.severity:blocker    allure.label.tag:auth    allure.label.tag:security
    ${user}=    Create Active Functional User    loginbad
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    WrongPass123!
    Click    role=button[name=/zaloguj/i]
    Page Should Have Text    Incorrect email or password.
    Wait For Function    () => window.location.pathname.includes('/login')
    Capture Test Screenshot

Injection Payload Does Not Authenticate Through Login Form
    [Tags]    auth    negative    security    critical    allure.label.story:Injection payload in login form is rejected safely    allure.label.severity:blocker    allure.label.tag:auth    allure.label.tag:security
    ${user}=    Create Active Functional User    loginxss
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    <script>alert(1)</script>
    Click    role=button[name=/zaloguj/i]
    Page Should Have Text    Incorrect email or password.
    Wait For Function    () => window.location.pathname.includes('/login')
    Capture Test Screenshot

Sql Injection Password Does Not Authenticate Through Login Form
    [Tags]    auth    negative    security    critical    allure.label.story:SQL injection password payload in login form is rejected safely    allure.label.severity:blocker    allure.label.tag:auth    allure.label.tag:security
    ${user}=    Create Active Functional User    loginsqli
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ' OR '1'='1' --
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/login')
    Page Should Have Text    FinancialManager
    Capture Test Screenshot

Fresh Backend Session Blocks Second Browser Login
    [Tags]    auth    negative    security    critical    allure.label.story:Second device login is blocked while a fresh session exists    allure.label.severity:blocker    allure.label.tag:auth    allure.label.tag:security
    ${user}=    Create Active Functional User    logindupe
    ${status}=    Start Functional Backend Session    ${user}
    Should Be Equal As Integers    ${status}    200
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Page Should Have Text    Konto jest już aktywne na innym urządzeniu.
    Wait For Function    () => window.location.pathname.includes('/login')
    Capture Test Screenshot
