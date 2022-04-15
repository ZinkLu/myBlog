import base64
from io import BytesIO
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import (Encoding, pkcs12)
from cryptography.x509 import load_pem_x509_certificate

# !pip install cryptography


class CAEncrypt:

    def load_private_key(self):
        """加载 pfx 中的秘钥对，用于生成签名"""
        with open(self._pfxfilepath, 'rb') as f:
            pfx_data = f.read()

        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(pfx_data, self._pfxkeypass)
        self.private_key = private_key
        self.certificate = certificate

    def __init__(self, cerfilepath: str, pfxfilepath: str, pfxkeypasspath: str) -> None:
        """
        :param cerfilepath: 公钥加密证书路径
        :param pfxfilepath: 签名证书路径
        :param pfxkeypass: 签名证书密码
        """
        self._cerfilepath = cerfilepath
        self._pfxfilepath = pfxfilepath
        with open(pfxkeypasspath, 'rb') as f:
            self._pfxkeypass = f.read()

        self._ras_cert = load_pem_x509_certificate(open(self._cerfilepath, "rb").read())
        self.load_private_key()

    def encrypt(self, content: bytes) -> bytes:
        """使用RSA公钥加密, 返回加密后的二进制"""
        public_key = self._ras_cert.public_key()
        max_block_size = public_key.key_size // 8 - 11
        rsa_padding = padding.PKCS1v15()

        if len(content) < max_block_size:
            return public_key.encrypt(content, rsa_padding)

        to_encrypt = BytesIO(content)
        encrypted = BytesIO()

        chuck = to_encrypt.read(max_block_size)
        while chuck:
            encrypted.write(public_key.encrypt(chuck, rsa_padding))
            chuck = to_encrypt.read(max_block_size)

        encrypted.seek(0)
        return encrypted.read()

    def signature(self, content: bytes) -> bytes:
        """RSA签名"""
        signeddata = self.private_key.sign(data=content, padding=padding.PKCS1v15(), algorithm=hashes.SHA1())
        return signeddata

    def encrypt_file(self, filepath: str, outpath: str):
        """加密文件
        1. 生成加密的内容
        2. 生成签名
        """
        outputdir = Path(outpath)
        outputdir.mkdir(parents=True, exist_ok=True)

        file = Path(filepath)
        if not file.exists() and not file.is_file():
            raise ValueError(f"{filepath} is not exist or not a valid file")

        content = file.read_bytes()
        no_prefix_filename = file.name.split('.')[0]

        encrypted_data = self.encrypt(content)  # 加密的二进制
        signeddata = self.signature(encrypted_data)
        b64_signeddata = base64.b64encode(signeddata)

        # 输出加密文件 + txt 文件
        encrypted_file = Path(outputdir / no_prefix_filename)
        encrypted_meta_file = Path(outputdir / (no_prefix_filename + '.txt'))

        cer_bytes = self.certificate.public_bytes(Encoding.DER)
        cer_string = base64.b64encode(cer_bytes).decode()

        with encrypted_file.open('wb') as ef, encrypted_meta_file.open('w', encoding='utf8') as emf:
            ef.write(encrypted_data)
            emf.writelines([cer_string + "\n", b64_signeddata.decode()])
