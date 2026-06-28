*** Settings ***
Documentation    Browser-level functional check for wallet snapshot creation and dashboard assets chart.
Library          Browser    timeout=15s    enable_playwright_debug=${False}
Library          ${CURDIR}/../TestKeywords/browser_keywords.py
Library          ${CURDIR}/../TestKeywords/auth_keywords.py
Library          ${CURDIR}/../TestKeywords/allure_helper.py    WITH NAME    AllureHelper
Suite Setup      Open Next Ui Browser
Suite Teardown   Close Browser And Keep Failure Artifacts
Test Setup       Reset Functional Auth Rate Limits
Test Tags        functional    next-ui    wallet    snapshots    dashboard    allure.label.epic:System Tests    allure.label.feature:Functional    allure.label.tag:functional    allure.label.tag:next-ui    allure.label.tag:wallet    allure.label.tag:snapshots    allure.label.severity:critical

*** Variables ***
${BASE_URL}        http://next.localhost
${HEADLESS}        True

*** Test Cases ***
User Can Create Snapshot And See Assets Chart
    [Tags]    critical    financial-data    allure.label.story:User creates a wallet snapshot and reaches nominal versus real assets dashboard    allure.label.severity:critical    allure.label.tag:financial-data
    ${user}=    Create Active Functional User    snapui
    ${wallet}=    Seed Functional Wallet Account    ${user}    1234.50
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/wallet')

    Go To Next Ui Path    /wallet-manager
    Page Should Have Heading    Zarządzanie portfelami
    Page Should Have Text    ${wallet}[wallet_name]
    Click    role=button[name=/Utwórz snapshot/i]
    Wait For Function    () => document.body.innerText.includes('Snapshot zapisany')

    Go To Next Ui Path    /wallet
    Page Should Have Text    AKTYWA: NOMINALNIE VS REALNIE
    Page Should Not Have Text    401 - Access Denied
    Page Should Not Have Text    Not authenticated
    Page Should Not Have Text    Brak portfeli do wyświetlenia
    Capture Test Screenshot
