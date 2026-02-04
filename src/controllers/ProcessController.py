import os
from .BaseController import BaseController
from .ProjectController import ProjectController
from langchain_pymupdf4llm import PyMuPDF4LLMLoader 
from langchain_community.document_loaders import Docx2txtLoader,TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

class ProcessController(BaseController):
    def __init__(self,project_id:str):
        super().__init__()
        self.project_id=project_id
        self.project_path=ProjectController().get_project_asset_path(project_id)
    def get_file_extension(self,file_id:str)->str:
        return file_id.split(".")[-1]
    
    def get_loader_by_extension(self,file_id:str):
        file_path=os.path.join(self.project_path,file_id)
        extension=self.get_file_extension(file_id)

        if extension in ["pdf","epub","mobi"]:
            return PyMuPDF4LLMLoader(file_path)
        elif extension == "txt":
            return TextLoader(file_path, encoding="utf-8")
        elif extension in ["docx"]:
            return Docx2txtLoader(file_path)
        else:
            raise ValueError(f"Unsupported file extension: {extension}")
    def load_document(self,file_id:str):
        loader=self.get_loader_by_extension(file_id)
        return loader.load()
    def process_document(self,file_content:list,file_id:str,chunk_size:int=1000,chunk_overlap:int=200):
        if not file_content:
            return [], [], []
        text_splitter=RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n","\n"," ",""],
            length_function=len
        )
        chunks=text_splitter.split_documents(file_content)
        file_content_texts=[
            rec.page_content
            for rec in chunks
        ]
        file_meta_data=[]
        for rec in chunks:
            meta = rec.metadata.copy()
            meta["file_id"] = file_id
            file_meta_data.append(meta)

        return chunks , file_content_texts, file_meta_data