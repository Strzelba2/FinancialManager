from fastapi import File, Form, HTTPException, UploadFile, status
from nicegui import app

from clients.stock_client import StockClient
from exceptions import MissingRequiredColumnsError
from imports.parsers import PARSERS


@app.get('/api/import/parsers')
async def list_import_parsers() -> list[dict]:
    return [
        {
            'name': parser.name,
            'kind': parser.kind,
            'accept': parser.accept,
            'upload_label': parser.upload_label,
            'supports_brokerage_events': getattr(parser, 'supports_brokerage_events', False),
            'supports_brokerage_history': getattr(parser, 'supports_brokerage_history', False),
            'supports_full_import': getattr(parser, 'supports_full_import', False),
        }
        for parser in PARSERS
    ]


@app.post('/api/import/parse')
async def parse_import_file(
    parser_name: str = Form(...),
    mode: str = Form('transactions'),
    file: UploadFile = File(...),
) -> dict:
    parser = next((item for item in PARSERS if item.name == parser_name), None)
    if parser is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Unknown parser')

    file_bytes = await file.read()

    try:
        if mode == 'brokerage_events':
            if not getattr(parser, 'supports_brokerage_events', False):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Selected parser does not support brokerage events')

            if parser.kind != 'CSV':
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Brokerage event import is available only for CSV formats')

            reader, _headers = parser.open_mb_dictreader_from_bytes(file_bytes)
            rows = await parser.parse_brokerage_events(reader, StockClient())
            payload = [row.model_dump(mode='json') for row in rows]
            return {'mode': mode, 'count': len(payload), 'rows': payload}

        if mode == 'brokerage_history':
            if not getattr(parser, 'supports_brokerage_history', False):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Selected parser does not support brokerage full history')

            if parser.kind != 'CSV':
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Brokerage full history import is available only for CSV formats')

            reader, _headers = parser.open_mb_dictreader_from_bytes(file_bytes)
            rows = await parser.parse_brokerage_history(reader, StockClient())
            payload = [row.model_dump(mode='json') for row in rows]
            return {'mode': mode, 'count': len(payload), 'rows': payload}

        if parser.kind == 'PDF':
            rows = parser.parse(file_bytes)
        else:
            reader, _headers = parser.open_mb_dictreader_from_bytes(file_bytes)
            rows = parser.parse(reader)

        payload = [row.model_dump(mode='json') for row in rows]
        return {'mode': 'transactions', 'count': len(payload), 'rows': payload}
    except HTTPException:
        raise
    except MissingRequiredColumnsError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
