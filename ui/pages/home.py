
from nicegui import ui, app
from fastapi import Request

from components.navbar_footer import nav, footer
from static.style import add_style


@ui.page('/home')
async def home(request: Request):
    session = request.cookies.get('sessionid')
    
    if session:
        if await app.storage.session.exists(request.cookies.get('sessionid')):
            ui.navigate.to("/wallet")
    
    add_style()
    nav("Home")
    with ui.element('section').classes('hero'):
        with ui.element('div').classes('hero-content'):
            ui.html('<h1>FinansowaEg</h1>')
            ui.html('<p>Zyskaj kontrolę nad swoim budżetem, śledź wydatki, planuj lepszą przyszłość.<br>'
                    '<span style="color: #666; font-size:0.97em;">'
                    'Dołącz do naszej społeczności i spraw, by Twoje pieniądze pracowały dla Ciebie!</span></p>')
            ui.html('''
                <div class="cta-buttons">
                    <a href="/register" class="cta-btn">Zarejestruj się</a>
                    <a href="/login" class="cta-btn alt">Zaloguj się</a>
                </div>
            ''')
            
    with ui.element('div').classes('features'):
        for img_url, title, desc in [
            ("https://img.icons8.com/color/48/000000/combo-chart--v1.png", 
             "Analizuj wydatki i przychody", "Szczegółowe wykresy i raporty pomagają lepiej zrozumieć Twoje finanse."),
            ("https://img.icons8.com/color/48/000000/money-bag.png", 
             "Planuj cele oszczędnościowe", "Ustalaj cele i obserwuj swoje postępy w odkładaniu środków."),
            ("https://img.icons8.com/color/48/000000/alarm.png", 
             "Otrzymuj powiadomienia", "Bądź na bieżąco z limitem wydatków i ważnymi terminami.")
        ]:
            with ui.element('div').classes('feature-box'):
                ui.image(img_url).style('width:48px; margin-bottom:14px;')
                ui.html(f'<div class="feature-title">{title}</div>')
                ui.html(f'<div class="feature-desc">{desc}</div>')

    with ui.element('section').classes('why-section'):
        ui.html('<h2>Dlaczego warto wybrać FinansowaEg?</h2>')
        ui.html('''
        <ul>
            <li>Intuicyjny interfejs – zacznij w minutę!</li>
            <li>Bezpieczne przechowywanie danych</li>
            <li>Pomoc ekspertów finansowych</li>
            <li>Możliwość eksportu raportów do PDF/Excel</li>
        </ul>
        ''')
    footer()
