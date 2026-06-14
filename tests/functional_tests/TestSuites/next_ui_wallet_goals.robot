*** Settings ***
Documentation    Browser-level functional check for annual wallet goals.
Library          Browser    timeout=15s    enable_playwright_debug=${False}
Library          ${CURDIR}/../TestKeywords/browser_keywords.py
Library          ${CURDIR}/../TestKeywords/auth_keywords.py
Library          ${CURDIR}/../TestKeywords/allure_helper.py    WITH NAME    AllureHelper
Suite Setup      Open Next Ui Browser
Suite Teardown   Close Browser And Keep Failure Artifacts
Test Setup       Reset Functional Auth Rate Limits
Test Tags        functional    next-ui    wallet    goals    allure.label.epic:System Tests    allure.label.feature:Functional    allure.label.tag:functional    allure.label.tag:next-ui    allure.label.tag:wallet    allure.label.tag:goals    allure.label.severity:critical

*** Variables ***
${BASE_URL}        http://next.localhost
${HEADLESS}        True

*** Test Cases ***
User Can Save Capital Gain Target From Wallet Goals Dialog
    [Tags]    critical    financial-data    allure.label.story:User saves annual income expense and capital gain goals through Next UI    allure.label.severity:critical    allure.label.tag:financial-data
    ${user}=    Create Active Functional User    goalsui
    ${wallet}=    Seed Functional Wallet Account    ${user}    100.00
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/wallet')

    Go To Next Ui Path    /wallet?modal=goals
    Page Should Have Text    Cele roczne
    Click    xpath=//button[normalize-space(.)="Dodaj"]
    Page Should Have Text    Dodaj / zaktualizuj cel
    Fill Text    css=input[placeholder="np. 120000"]    200000
    Fill Text    css=input[placeholder="np. 80000"]    90000
    Fill Text    css=input[placeholder="np. 24000"]    60000
    Click    xpath=//button[normalize-space(.)="Zapisz"]
    Wait For Function    () => !document.body.innerText.includes('Zapisywanie…')
    Wait For Function    () => Array.from(document.querySelectorAll('input')).some((input) => input.value === '60000.00')
    Page Should Have Text    ${wallet}[wallet_name]
    Page Should Have Text    Cel zysku kap.
    Capture Test Screenshot
