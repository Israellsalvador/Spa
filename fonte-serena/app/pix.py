"""Geração do Pix Copia e Cola (BR Code estático com valor) e do QR Code."""
import re
import unicodedata

import segno


def _campo(id_, valor):
    return f"{id_}{len(valor):02d}{valor}"


def _limpar(texto, limite):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^A-Za-z0-9 .\-]", "", texto).strip()
    return texto[:limite]


def _crc16(payload):
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def normalizar_chave(chave):
    chave = (chave or "").strip()
    # Telefone: o padrão Pix exige +55DDDNUMERO
    digitos = re.sub(r"\D", "", chave)
    if re.fullmatch(r"\+?55\d{10,11}", chave.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")):
        return "+" + digitos
    return chave


def copia_e_cola(chave, nome, cidade, valor_centavos, txid):
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", normalizar_chave(chave))
    txid = re.sub(r"[^A-Za-z0-9]", "", txid or "")[:25] or "***"
    payload = (
        _campo("00", "01")
        + _campo("26", conta)
        + _campo("52", "0000")
        + _campo("53", "986")
        + _campo("54", f"{valor_centavos / 100:.2f}")
        + _campo("58", "BR")
        + _campo("59", _limpar(nome, 25) or "RECEBEDOR")
        + _campo("60", _limpar(cidade, 15) or "BRASIL")
        + _campo("62", _campo("05", txid))
        + "6304"
    )
    return payload + _crc16(payload)


def qr_svg(payload):
    return segno.make(payload, error="m").svg_inline(scale=6, border=2, dark="#211C18", light="#FFFFFF")
