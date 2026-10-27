import base64
import io
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from PIL import Image

from app import creation_tools
from tests.test_reference_tools import encode


@pytest.mark.asyncio
async def test_crop_is_segmented_before_inference_and_mask_returns_to_source_coordinates(monkeypatch):
    source=Image.new('RGB',(200,100),(30,40,50))
    source.putpixel((84,20),(240,160,50))
    async def read(n):return encode(source)
    async def post(self,url,**kwargs):
        assert url.endswith('/prepare-image')
        selected=Image.open(io.BytesIO(base64.b64decode(kwargs['json']['image_base64']))).convert('RGBA')
        assert selected.size==(120,80)
        assert selected.getpixel((44,10))==(240,160,50,255)
        selected.putalpha(180)
        return httpx.Response(200,content=encode(selected),headers={'X-Foreground-Model':'u2net'})
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    result=await creation_tools.remove_background(SimpleNamespace(read=read),object(),'u2net',json.dumps({'x':20,'y':10,'width':60,'height':80}))
    output=Image.open(io.BytesIO(result.body))
    assert output.size==source.size
    assert output.getpixel((84,20))==(240,160,50,180)
    assert output.getpixel((0,0))[3]==0 and output.getpixel((190,90))[3]==0
    assert result.headers['X-Foreground-Model']=='u2net'


@pytest.mark.asyncio
@pytest.mark.parametrize('crop',['broken','{"x":90,"y":0,"width":20,"height":50}','{"x":0,"y":0,"width":0,"height":50}','{"x":0,"y":0,"width":100,"height":100,"unexpected":1}'])
async def test_invalid_crop_never_calls_segmentation(monkeypatch,crop):
    async def read(n):return encode(Image.new('RGB',(20,20),'white'))
    async def no_call(*a,**kw):pytest.fail('Invalid crop must not call inference')
    monkeypatch.setattr(httpx.AsyncClient,'post',no_call)
    with pytest.raises(HTTPException) as failure:
        await creation_tools.remove_background(SimpleNamespace(read=read),object(),'u2net',crop)
    assert failure.value.status_code==422
