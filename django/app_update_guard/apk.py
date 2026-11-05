"""Leitura do AndroidManifest.xml binário de um APK, sem dependências externas.

Extrai somente o pacote, o versionCode e o versionName do elemento <manifest>.
Assim, a versão cadastrada é sempre a do arquivo enviado, e um erro de digitação
não deixa os colaboradores presos em um pedido de atualização sem fim.
"""
import struct
import zipfile
from dataclasses import dataclass

RES_STRING_POOL_TYPE = 0x0001
RES_XML_TYPE = 0x0003
RES_XML_START_ELEMENT_TYPE = 0x0102
RES_XML_RESOURCE_MAP_TYPE = 0x0180
UTF8_FLAG = 0x100
TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10
TYPE_INT_HEX = 0x11
NO_INDEX = 0xFFFFFFFF
# IDs dos atributos android:versionCode e android:versionName (APKs ofuscados
# podem omitir o nome do atributo e manter apenas o ID do recurso).
ATTR_VERSION_CODE = 0x0101021B
ATTR_VERSION_NAME = 0x0101021C


class ApkInvalido(ValueError):
    pass


@dataclass(frozen=True)
class ManifestoApk:
    pacote: str
    codigo_versao: int | None
    versao: str | None


def _ler_strings(dados, inicio):
    _, header_size, _ = struct.unpack_from("<HHI", dados, inicio)
    quantidade, _, flags, strings_start, _ = struct.unpack_from("<IIIII", dados, inicio + 8)
    offsets = struct.unpack_from(f"<{quantidade}I", dados, inicio + header_size)
    base = inicio + strings_start
    utf8 = bool(flags & UTF8_FLAG)
    strings = []
    for offset in offsets:
        pos = base + offset
        if utf8:
            # Comprimento em caracteres e depois em bytes; cada um com 1 ou 2 bytes.
            pos += 2 if dados[pos] & 0x80 else 1
            tamanho = dados[pos]
            if tamanho & 0x80:
                tamanho = ((tamanho & 0x7F) << 8) | dados[pos + 1]
                pos += 2
            else:
                pos += 1
            strings.append(dados[pos:pos + tamanho].decode("utf-8", errors="replace"))
        else:
            tamanho = struct.unpack_from("<H", dados, pos)[0]
            pos += 2
            if tamanho & 0x8000:
                tamanho = ((tamanho & 0x7FFF) << 16) | struct.unpack_from("<H", dados, pos)[0]
                pos += 2
            strings.append(dados[pos:pos + tamanho * 2].decode("utf-16-le", errors="replace"))
    return strings


def ler_manifesto_binario(dados):
    try:
        tipo, header_size, _ = struct.unpack_from("<HHI", dados, 0)
        if tipo != RES_XML_TYPE:
            raise ApkInvalido("O manifesto do APK não está no formato binário esperado.")
        strings, recursos = [], []
        pos = header_size
        while pos + 8 <= len(dados):
            tipo, header_size, tamanho = struct.unpack_from("<HHI", dados, pos)
            if tamanho < 8:
                break
            if tipo == RES_STRING_POOL_TYPE:
                strings = _ler_strings(dados, pos)
            elif tipo == RES_XML_RESOURCE_MAP_TYPE:
                recursos = list(struct.unpack_from(f"<{(tamanho - header_size) // 4}I", dados, pos + header_size))
            elif tipo == RES_XML_START_ELEMENT_TYPE:
                _, nome, attr_start, attr_size, attr_count = struct.unpack_from("<IIHHH", dados, pos + header_size)
                if strings[nome] != "manifest":
                    break
                valores = {}
                for indice in range(attr_count):
                    attr = pos + header_size + attr_start + indice * attr_size
                    _, nome_attr, bruto, _, _, tipo_dado, dado = struct.unpack_from("<IIIHBBI", dados, attr)
                    chave = strings[nome_attr] if nome_attr < len(strings) else ""
                    if nome_attr < len(recursos):
                        chave = {ATTR_VERSION_CODE: "versionCode", ATTR_VERSION_NAME: "versionName"}.get(recursos[nome_attr], chave)
                    if tipo_dado in {TYPE_INT_DEC, TYPE_INT_HEX}:
                        valores[chave] = dado
                    elif bruto != NO_INDEX:
                        valores[chave] = strings[bruto]
                    elif tipo_dado == TYPE_STRING:
                        valores[chave] = strings[dado]
                pacote = valores.get("package")
                if not isinstance(pacote, str) or not pacote:
                    raise ApkInvalido("O manifesto do APK não informa o pacote do aplicativo.")
                codigo = valores.get("versionCode")
                if isinstance(codigo, str):
                    codigo = int(codigo) if codigo.isdigit() else None
                versao = valores.get("versionName")
                return ManifestoApk(pacote, codigo, versao if isinstance(versao, str) and versao else None)
            pos += tamanho
    except (struct.error, IndexError, UnicodeError) as exc:
        raise ApkInvalido("Não foi possível ler o manifesto do APK.") from exc
    raise ApkInvalido("O manifesto do APK não contém o elemento <manifest>.")


def ler_apk(arquivo):
    """Valida o pacote ZIP e retorna os dados do manifesto."""
    posicao = arquivo.tell() if hasattr(arquivo, "tell") else None
    try:
        with zipfile.ZipFile(arquivo) as pacote:
            try:
                info = pacote.getinfo("AndroidManifest.xml")
            except KeyError as exc:
                raise ApkInvalido("O arquivo não contém um AndroidManifest.xml; envie o APK gerado para Android.") from exc
            if info.file_size > 10 * 1024 * 1024:
                raise ApkInvalido("O manifesto do APK é maior que o permitido.")
            return ler_manifesto_binario(pacote.read(info))
    except zipfile.BadZipFile as exc:
        raise ApkInvalido("O arquivo enviado não é um APK válido.") from exc
    finally:
        if posicao is not None:
            arquivo.seek(posicao)
