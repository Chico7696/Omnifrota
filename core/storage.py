import hashlib  # Calcula identificadores estáveis a partir do conteúdo do arquivo.
import posixpath  # Trata caminhos de mídia com separadores padronizados.

from django.core.files.storage import FileSystemStorage  # Usa o armazenamento local do Django como base.


class DeduplicatingImageStorage(FileSystemStorage):  # Armazena uma única cópia de imagens com conteúdo idêntico.
    def save(self, name, content, max_length=None):  # Calcula o caminho final antes de gravar o arquivo.
        digest = hashlib.sha256()  # Inicializa o hash usado para identificar o conteúdo.
        for chunk in content.chunks():  # Processa o arquivo em blocos para limitar o uso de memória.
            digest.update(chunk)  # Acrescenta cada bloco ao hash.
        content.seek(0)  # Reposiciona o arquivo para que possa ser gravado pelo backend.

        name = name.replace('\\', '/')  # Normaliza separadores recebidos no nome.
        directory = posixpath.dirname(name)  # Mantém o diretório de destino configurado.
        extension = posixpath.splitext(name)[1].lower()  # Preserva a extensão em minúsculas.
        hashed_name = posixpath.join(directory, f'{digest.hexdigest()}{extension}')  # Usa o hash no nome do arquivo.
        if self.exists(hashed_name):  # Verifica se o mesmo conteúdo já foi salvo.
            return hashed_name  # Reutiliza o caminho existente sem duplicar o arquivo.
        return super().save(hashed_name, content, max_length=max_length)  # Persiste a primeira ocorrência.
