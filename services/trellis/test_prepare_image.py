import base64
import io
import pytest
from PIL import Image
import app


def payload(alpha=255):
    image=Image.new('RGBA',(24,32),(210,80,60,alpha))
    stream=io.BytesIO();image.save(stream,'PNG')
    return app.PrepareImageRequest(image_base64=base64.b64encode(stream.getvalue()).decode())


def test_alpha_foreground_returns_png_without_generation(monkeypatch):
    monkeypatch.setattr(app,'_run_local_comfyui_inference',lambda *args: pytest.fail('Must not generate a model'))
    result=app.prepare_image(payload(alpha=128))
    assert result.media_type=='image/png'
    image=Image.open(io.BytesIO(result.body))
    assert image.mode=='RGBA' and image.getchannel('A').getextrema()==(128,128)


def test_opaque_foreground_and_busy_lock(monkeypatch):
    calls=[]
    def prepare(path,**kwargs):
        assert kwargs['model']=='isnet-anime'
        calls.append(path)
        image=Image.open(path).convert('RGBA');image.putalpha(120);image.save(path)
        return path
    monkeypatch.setattr(app,'_prepare_comfy_input',prepare)
    result=app.prepare_image(payload())
    assert len(calls)==1 and Image.open(io.BytesIO(result.body)).getchannel('A').getextrema()==(120,120)
    app.prepare_lock.acquire()
    try:
        with pytest.raises(app.HTTPException) as failure: app.prepare_image(payload())
        assert failure.value.status_code==429
    finally: app.prepare_lock.release()


def test_invalid_base64_and_released_lock():
    with pytest.raises(app.HTTPException) as failure:
        app.prepare_image(app.PrepareImageRequest(image_base64='not base64!'))
    assert failure.value.status_code==422
    assert app.prepare_lock.acquire(blocking=False)
    app.prepare_lock.release()
