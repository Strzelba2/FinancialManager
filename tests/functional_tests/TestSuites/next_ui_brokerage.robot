*** Settings ***
Documentation    Browser-level brokerage flow check for next-ui.
Library          Browser    timeout=15s    enable_playwright_debug=${False}
Library          OperatingSystem
Library          String
Library          ${CURDIR}/../TestKeywords/browser_keywords.py
Library          ${CURDIR}/../TestKeywords/auth_keywords.py
Library          ${CURDIR}/../TestKeywords/allure_helper.py    WITH NAME    AllureHelper
Suite Setup      Open Next Ui Browser
Suite Teardown   Close Browser And Keep Failure Artifacts
Test Setup       Reset Functional Auth Rate Limits
Test Tags        functional    next-ui    wallet    brokerage    allure.label.epic:System Tests    allure.label.feature:Functional    allure.label.tag:functional    allure.label.tag:next-ui    allure.label.tag:wallet    allure.label.tag:brokerage    allure.label.severity:critical

*** Variables ***
${BASE_URL}              http://next.localhost
${HEADLESS}              True
${BOSSA_REVIEW_CSV}      ${CURDIR}/../fixtures/bossa_needs_review.csv
${BOSSA_VALID_TEMPLATE}  ${CURDIR}/../fixtures/bossa_valid_history.csv

*** Test Cases ***
User Can Manage Brokerage Event And Bossa History Import Guards
    [Tags]    critical    financial-data    allure.label.story:User manages brokerage events and guarded BoSSA imports through Next UI    allure.label.severity:critical    allure.label.tag:financial-data
    ${user}=    Create Active Functional User    brkui
    ${wallet}=    Seed Functional Wallet Account    ${user}    0.00
    ${brokerage}=    Seed Functional Brokerage Account    ${wallet}    10000.00
    ${template}=    Get File    ${BOSSA_VALID_TEMPLATE}
    ${valid_csv}=    Replace String    ${template}    __SYMBOL__    ${brokerage}[symbol]
    ${valid_csv}=    Replace String    ${valid_csv}    __ISIN__    ${brokerage}[isin]
    ${valid_csv_path}=    Set Variable    ${OUTPUT DIR}/bossa_valid_${brokerage}[symbol].csv
    Create File    ${valid_csv_path}    ${valid_csv}

    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/wallet')

    Go To Next Ui Path    /wallet?modal=transaction
    Click    xpath=//div[@role="dialog"]//button[normalize-space(.)="Makler"]
    Page Should Have Text    Rachunek maklerski
    Click    xpath=(//div[@role="dialog"]//button[@role="combobox"])[2]
    Click    xpath=//*[@role="option"][contains(normalize-space(.), "${brokerage}[mic]")]
    Fill Text    css=input[placeholder="Szukaj po symbolu lub nazwie"]    ${brokerage}[symbol]
    Click    xpath=(//div[@role="dialog"]//button[@role="combobox"])[3]
    Click    xpath=//*[@role="option"][contains(normalize-space(.), "${brokerage}[symbol]")]
    Fill Text    xpath=//label[normalize-space(.)='Ilość']/following::input[1]    1
    Fill Text    xpath=//label[normalize-space(.)='Cena / kwota']/following::input[1]    100
    Click    text=Wybierz datę i godzinę
    Click    role=button[name=/Teraz/i]
    Click    role=button[name=/Dodaj operację/i]
    Wait For Function    () => !document.body.innerText.includes('Zapisywanie…')
    Page Should Not Have Text    Nie udało się zapisać operacji maklerskiej

    Go To Next Ui Path    /brokerage/holdings
    Wait For Function    () => document.body.innerText.includes('${brokerage}[symbol]')
    Click    role=button[name=/Split lub korekta ${brokerage}[symbol]/i]
    Fill Text    css=#holding-action-split-ratio    2
    Click    role=button[name=/Zapisz/i]
    Wait For Function    () => Array.from(document.querySelectorAll('tr')).some((row) => row.innerText.includes('${brokerage}[symbol]') && row.innerText.includes('2'))

    Go To Next Ui Path    /wallet?modal=transaction
    Click    xpath=//div[@role="dialog"]//button[normalize-space(.)="Import CSV"]
    Click    xpath=(//div[@role="dialog"]//button[@role="combobox"])[1]
    Click    xpath=//*[@role="option"][contains(normalize-space(.), "BossaMakler CSV")]
    Page Should Have Text    Pełna historia maklerska
    Upload File By Selector    css=input[type="file"]    ${BOSSA_REVIEW_CSV}
    Click    role=button[name=/Przetwórz plik/i]
    Page Should Have Text    Podgląd historii BoSSA
    Page Should Have Text    NEEDS_REVIEW
    Wait For Function    () => document.body.innerText.includes('MISSING')
    Wait For Function    () => Array.from(document.querySelectorAll('button')).some((button) => button.innerText.trim() === 'Importuj' && button.disabled)

    Upload File By Selector    css=input[type="file"]    ${valid_csv_path}
    Click    role=button[name=/Przetwórz plik/i]
    Wait For Function    () => document.body.innerText.includes('${brokerage}[symbol]')
    Click    role=button[name=/Importuj/i]
    Wait For Function    () => !document.body.innerText.includes('Importowanie…')
    Page Should Have Text    utworzono:
    Capture Test Screenshot
