import io

import numpy as np
from PIL import Image, ImageDraw
import pytest

from app.reference_tools import analyze_reference,validate_generation_reference
from app.security import create_access_token
from tests.test_studio import seed


def encode(image,fmt='PNG',**kwargs):
    stream=io.BytesIO();image.save(stream,fmt,**kwargs);return stream.getvalue()


def test_simple_colored_background_estimates_framing_without_mandating_cutout():
    image=Image.new('RGB',(400,600),(50,90,120))
    draw=ImageDraw.Draw(image)
    draw.rectangle((150,100,250,500),fill=(180,110,90))
    result=analyze_reference(encode(image))
    assert result['background_kind']=='simple'
    assert result['background_color']=='#325a78'
    assert result['framing_method']=='border-connected'
    assert 35<result['subject_bounds']['x']<40
    assert 80<result['subject_bounds']['bottom']<86
    assert result['edge_contact']==[]
    assert '保留简单背景' in result['recommendation']


def test_native_alpha_keeps_detached_accessories_and_warns_about_edge_contact():
    image=Image.new('RGBA',(400,600),(0,0,0,0))
    draw=ImageDraw.Draw(image)
    draw.rectangle((150,40,250,599),fill=(180,110,90,255))
    draw.rectangle((20,200,35,230),fill=(200,200,10,255))
    result=analyze_reference(encode(image))
    assert result['framing_method']=='alpha'
    assert result['subject_bounds']['x']<6
    assert result['subject_bounds']['bottom']==100
    assert '下方' in result['edge_contact']


def test_complex_scene_does_not_invent_a_person_mask_or_auto_crop():
    image=Image.fromarray(np.random.default_rng(7).integers(0,256,(280,420,3),dtype=np.uint8))
    result=analyze_reference(encode(image))
    assert result['subject_bounds'] is None
    assert result['framing_method']=='uncertain'
    assert '保留整图' in result['recommendation']
    assert 'uncertain-background' in {item['code'] for item in result['warnings']}


def test_exif_orientation_and_low_resolution_are_not_hallucinated_detail():
    image=Image.new('RGB',(120,240),'white')
    exif=Image.Exif();exif[274]=6
    result=analyze_reference(encode(image,'JPEG',exif=exif))
    assert (result['width'],result['height'])==(240,120)
    assert 'low-resolution' in {item['code'] for item in result['warnings']}


@pytest.mark.parametrize('data',[b'invalid',encode(Image.new('RGBA',(8,8),(0,0,0,0)))])
def test_empty_or_invalid_reference_is_rejected(data):
    with pytest.raises(ValueError):analyze_reference(data)


def test_transparent_foreground_is_valid_even_when_original_has_complex_background():
    original=encode(Image.fromarray(np.random.default_rng(7).integers(0,256,(100,80,3),dtype=np.uint8)))
    foreground=Image.new('RGBA',(100,100),(0,0,0,0))
    ImageDraw.Draw(foreground).rectangle((25,20,75,95),fill=(200,120,90,255))
    result=validate_generation_reference(encode(foreground),original)
    assert result['background_kind']=='alpha' and result['original_background_kind']=='complex'


@pytest.mark.asyncio
async def test_analysis_endpoint_is_private_and_does_not_require_gpu_service(client,db_session,monkeypatch):
    from app import creation_tools
    owner,*_=await seed(db_session)
    def no_network(*a,**kw):pytest.fail('Pixel analysis must not call a model or generation service')
    monkeypatch.setattr(creation_tools.httpx,'AsyncClient',no_network)
    files={'image':('reference.png',encode(Image.new('RGB',(50,80),'white')),'image/png')}
    url='/api/v1/studio/images/analyze-reference'
    assert (await client.post(url,files=files)).status_code==401
    headers={'Authorization':f'Bearer {create_access_token(owner.id)}'}
    response=await client.post(url,files=files,headers=headers)
    assert response.status_code==200 and response.json()['version']==2
    invalid=await client.post(url,files={'image':('bad.png',b'bad','image/png')},headers=headers)
    assert invalid.status_code==422
