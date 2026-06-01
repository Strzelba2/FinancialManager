*** Settings ***
Documentation    Browser-level functional transaction lifecycle check for next-ui.
Library          Browser    timeout=15s    enable_playwright_debug=${False}
Library          ${CURDIR}/../TestKeywords/browser_keywords.py
Library          ${CURDIR}/../TestKeywords/auth_keywords.py
Library          ${CURDIR}/../TestKeywords/allure_helper.py    WITH NAME    AllureHelper
Suite Setup      Open Next Ui Browser
Suite Teardown   Close Browser And Keep Failure Artifacts
Test Setup       Reset Functional Auth Rate Limits
Test Tags        functional    next-ui    wallet    transactions    allure.label.epic:System Tests    allure.label.feature:Functional    allure.label.tag:functional    allure.label.tag:next-ui    allure.label.tag:wallet    allure.label.tag:transactions    allure.label.severity:critical

*** Variables ***
${BASE_URL}        http://next.localhost
${HEADLESS}        True
${CSV_FIXTURE}     ${CURDIR}/../fixtures/transactions_mbank.csv

*** Test Cases ***
User Can Manage Transaction Lifecycle From Wallet And Transactions Pages
    [Tags]    critical    financial-data    allure.label.story:User manages manual and imported transactions through Next UI    allure.label.severity:critical    allure.label.tag:financial-data
    ${user}=    Create Active Functional User    txui
    ${wallet}=    Seed Functional Wallet Account    ${user}    100.00
    Go To Next Ui Path    /login
    Fill Text    input[name="email"]    ${user}[email]
    Fill Text    input[name="password"]    ${user}[password]
    Click    role=button[name=/zaloguj/i]
    Wait For Function    () => window.location.pathname.includes('/wallet')

    Go To Next Ui Path    /wallet?modal=transaction
    Page Should Have Heading    Transakcje
    Fill Text    css=input[placeholder*="-120.50"]    100,00
    Fill Text    css=input[placeholder*="5140.30"]    200,00
    Fill Text    css=input[placeholder*="Biedronka"]    Manual functional salary
    Click    text=Wybierz datę i godzinę
    Click    role=button[name=/Teraz/i]
    Click    role=button[name=/Dodaj transakcję/i]
    Wait For Function    () => !document.body.innerText.includes('Dodawanie…')
    Page Should Not Have Text    Nie udało się dodać transakcji

    Go To Next Ui Path    /wallet?modal=transaction
    Click    text=Import CSV
    Page Should Have Text    Format banku
    Page Should Have Text    mBank CSV
    Upload File By Selector    css=input[type="file"]    ${CSV_FIXTURE}
    Click    role=button[name=/Przetwórz plik/i]
    Page Should Have Text    Podgląd transakcji
    Page Should Have Text    Zakupy functional CSV import
    Click    role=button[name=/Importuj/i]
    Wait For Function    () => !document.body.innerText.includes('Importowanie…')
    Page Should Not Have Text    Nie udało się zaimportować transakcji

    Go To Next Ui Path    /transactions
    Fill Text    css=input[placeholder="Szukaj…"]    Zakupy functional
    Page Should Have Text    Zakupy functional CSV import
    Click    css=tbody tr:first-child td:nth-child(4) span
    Click    text=Żywność
    Click    css=tbody tr:first-child td:nth-child(5) span
    Click    text=Wydatek
    Click    role=button[name=/Zapisz/i]
    Wait For Function    () => Array.from(document.querySelectorAll('button')).some((button) => button.innerText.trim() === 'Zapisz' && button.disabled)
    Wait For Function    () => document.body.innerText.includes('Żywność') && document.body.innerText.includes('Wydatek')
    Click    css=tbody tr:first-child td:last-child button
    Page Should Have Text    Czy na pewno usunąć?
    Click    css=tbody tr:first-child td:last-child button:first-child
    Wait For Function    () => document.body.innerText.includes('Brak transakcji spełniających kryteria')
    Capture Test Screenshot
