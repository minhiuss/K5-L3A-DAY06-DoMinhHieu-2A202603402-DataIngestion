"""Implement fixed-size and structure-aware chunking."""
from .models import Chunk, DocumentPage


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split text into overlapping windows and retain page metadata."""
    chunks = []
    step = size - overlap
    for number, start in enumerate(range(0, len(page.text), step)):
        piece = page.text[start:start + size]
        chunks.append(Chunk(
            chunk_id=f"A:{page.page}:{page.metadata.get('section','')}:{number}",
            document_id=page.document_id,
            source=page.source,
            page=page.page,
            text=piece,
            metadata=dict(page.metadata),
        ))
        if start + size >= len(page.text):
            break
    return chunks

def split_paragraphs(text: str, short: int = 90) -> list[str]: # what is ->
    paragraphs = [] # we start with blank list of finished paragraphs and currents 
    current = [] # current when built becomes paragraph
    for line in text.splitlines(): # loop each line in the text, split by each line
        current.append(line) # append a line to current, rinse and repeat until created paragraph
        if len(line) < short: # if line too short (under 90 words or whatever the number), trigger appending current to para, end para after appending
            paragraphs.append(" ".join(current)) # append whatever text in current to para
            current = [] # cuz appended to para so current got cleared
    if current: # wait how this trigger i mean for loop up there dont have break or return or sth to stop? the result is the same though when would this run? like when theres only 1 sentence under 90 words in a paragraph? 
        paragraphs.append(" ".join(current))
    return paragraphs # okay


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """group paragraphs, split oversized paragraphs and retain metadata."""
    blocks = []
    texts = []
    current = ""

    for paragraph in split_paragraphs(page.text): 
        for text in range(0, len(paragraph), max_size):
            blocks.append(paragraph[text:text+max_size])

    for block in blocks: 
        if current != "" and len(current) + 1 + len(block) > max_size: 
            texts.append(current)
            current = block
        elif current != "":
            current = current + "\n" + block
        else: 
            current = block
    if current != "":
        texts.append(current)

    chunks = []
    for number, text in enumerate(texts):
        chunks.append(Chunk(
            chunk_id=f"B:{page.page}:{page.metadata.get('section','')}:{number}",
                        document_id=page.document_id,  
                        source=page.source,            
                        page=page.page,                
                        text=text,                    
                        metadata=dict(page.metadata),  
                    ))
    return chunks

