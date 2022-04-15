import base64
from io import BytesIO
from pathlib import Path

from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_der_x509_certificate
from cryptography.exceptions import InvalidSignature


class CADecrypt:

    def __init__(self, pfxfilepath: str, pfxkeypasspath: str) -> None:
        """pfx和密码
        :param: pfxfilepath        pfx文件
        :param: pfxkeypasspath    密码文件
        """
        self._pfxfilepath = pfxfilepath

        with open(pfxkeypasspath, 'rb') as f:
            self._pfxkeypass = f.read()

        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
            open(pfxfilepath, "rb").read(),
            self._pfxkeypass,
        )
        self.private_key = private_key  # 私钥
        self.certificate = certificate  # 公钥

    def decrypt(self, content: bytes) -> bytes:
        max_block_size = self.private_key.key_size // 8
        pkcs1v15_padding = padding.PKCS1v15()

        to_decrypt = BytesIO(content)
        decrypted = BytesIO()

        chuck = to_decrypt.read(max_block_size)

        while chuck:
            buffer = self.private_key.decrypt(chuck, pkcs1v15_padding)
            decrypted.write(buffer)
            chuck = to_decrypt.read(max_block_size)

        decrypted.seek(0)
        return decrypted.read()

    def rsa_verify_signature(self, encrypted_file_path: str, encrypted_meta_path: str) -> bool:
        encrypted_file = Path(encrypted_file_path)
        encrypted_meta = Path(encrypted_meta_path)

        meta = encrypted_meta.read_text().strip()
        meta_list = meta.split("\n")
        if len(meta_list) != 2:
            raise ValueError("meta data length wrong, length is %s" % len(meta_list))

        cer_64data, signed_64data = meta_list

        cer_data = base64.b64decode(cer_64data)
        signed_data = base64.b64decode(signed_64data)

        public_key = load_der_x509_certificate(cer_data)

        try:
            public_key.public_key().verify(
                signed_data,
                encrypted_file.read_bytes(),
                padding.PKCS1v15(),
                hashes.SHA1(),
            )
        except InvalidSignature as e:
            print(e)
            return False
        else:
            return True

    def rsa_verify_and_decrypt(self, encrypted_file_path: str, encrypted_meta_path: str) -> bytes:
        if not self.rsa_verify_signature(encrypted_file_path, encrypted_meta_path):
            raise ValueError("签名不正确")
        return self.decrypt(open(encrypted_file_path, 'rb').read())
