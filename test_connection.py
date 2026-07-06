from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

llm = ChatOpenAI(model="gpt-4o-mini")
print(llm.invoke("Say 'connection OK' and nothing else.").content)

emb = OpenAIEmbeddings(model="text-embedding-3-small")
vec = emb.embed_query("hello world")
print(f"Embedding OK — vector dimension: {len(vec)}")
