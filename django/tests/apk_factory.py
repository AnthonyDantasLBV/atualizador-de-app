"""Gera APKs mínimos com AndroidManifest.xml binário, como o produzido pelo aapt."""
import io
import struct
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile

from app_update_guard.apk import ATTR_VERSION_CODE, ATTR_VERSION_NAME


def _chunk(tipo, header, corpo):
    header_size = 8 + len(header)
    return struct.pack("<HHI", tipo, header_size, header_size + len(corpo)) + header + corpo


def _string_pool(strings, utf8=False):
    dados, offsets = b"", []
    for texto in strings:
        offsets.append(len(dados))
        if utf8:
            codificado = texto.encode("utf-8")
            dados += bytes([len(texto), len(codificado)]) + codificado + b"\x00"
        else:
            dados += struct.pack("<H", len(texto)) + texto.encode("utf-16-le") + b"\x00\x00"
    dados += b"\x00" * (-len(dados) % 4)
    offsets_bin = struct.pack(f"<{len(offsets)}I", *offsets)
    strings_start = 28 + len(offsets_bin)
    header = struct.pack("<IIIII", len(strings), 0, 0x100 if utf8 else 0, strings_start, 0)
    return _chunk(0x0001, header, offsets_bin + dados)


def manifesto_binario(pacote="com.exemplo.app", codigo=5, versao="1.2.0", utf8=False, nomes_ofuscados=False):
    nome_code = "" if nomes_ofuscados else "versionCode"
    nome_name = "" if nomes_ofuscados else "versionName"
    strings = [nome_code, nome_name, "package", "manifest", pacote, versao, "android"]
    pool = _string_pool(strings, utf8)
    mapa = _chunk(0x0180, b"", struct.pack("<II", ATTR_VERSION_CODE, ATTR_VERSION_NAME))
    atributos = [
        struct.pack("<IIIHBBI", 6, 0, 0xFFFFFFFF, 8, 0, 0x10, codigo),
        struct.pack("<IIIHBBI", 6, 1, 5, 8, 0, 0x03, 5),
        struct.pack("<IIIHBBI", 0xFFFFFFFF, 2, 4, 8, 0, 0x03, 4),
    ]
    ext = struct.pack("<IIHHHHHH", 0xFFFFFFFF, 3, 20, 20, len(atributos), 0, 0, 0)
    elemento = _chunk(0x0102, struct.pack("<II", 1, 0xFFFFFFFF), ext + b"".join(atributos))
    corpo = pool + mapa + elemento
    return struct.pack("<HHI", 0x0003, 8, 8 + len(corpo)) + corpo


def apk_bytes(**kwargs):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("AndroidManifest.xml", manifesto_binario(**kwargs))
        pacote.writestr("classes.dex", b"dex\n035\x00")
    return buffer.getvalue()


def apk_upload(nome="app-release.apk", **kwargs):
    return SimpleUploadedFile(nome, apk_bytes(**kwargs), content_type="application/vnd.android.package-archive")
