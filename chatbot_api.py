from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client
import json
import os
from pypdf import PdfReader

load_dotenv(override=True)

app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend


class RAGRetriever:
    """Handles vector embeddings and similarity search"""
    
    def __init__(self, openai_client, supabase_client):
        self.openai = openai_client
        self.supabase = supabase_client
    
    def is_initialized(self):
        """Check if documents are already embedded"""
        try:
            result = self.supabase.table('documents').select('id').limit(1).execute()
            return len(result.data) > 0
        except:
            return False
    
    def generate_embedding(self, text):
        """Generate embedding using OpenAI"""
        response = self.openai.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding
    
    def chunk_text(self, text, source, chunk_size=500):
        """Split text into semantic chunks"""
        sections = [s.strip() for s in text.split('\n\n') if s.strip()]
        chunks = []
        
        for i, section in enumerate(sections):
            if len(section) > 50:  # Minimum chunk size
                chunks.append({
                    'content': section,
                    'metadata': {'source': source, 'chunk_id': i}
                })
        
        return chunks
    
    def embed_documents(self, resume, summary):
        """Chunk and embed documents into vector store"""
        chunks = self.chunk_text(resume, source="resume")
        chunks.extend(self.chunk_text(summary, source="summary"))
        
        print(f"Embedding {len(chunks)} document chunks...")
        
        for chunk in chunks:
            embedding = self.generate_embedding(chunk['content'])
            self.supabase.table('documents').insert({
                'content': chunk['content'],
                'metadata': chunk['metadata'],
                'embedding': embedding
            }).execute()
        
        print(f"✓ Embedded {len(chunks)} chunks successfully")
    
    def retrieve_context(self, query, top_k=3):
        """Retrieve most relevant chunks using vector similarity"""
        try:
            query_embedding = self.generate_embedding(query)
            
            response = self.supabase.rpc(
                'match_documents',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': 0.7,
                    'match_count': top_k
                }
            ).execute()
            
            return [doc['content'] for doc in response.data]
        except Exception as e:
            print(f"RAG retrieval error: {e}")
            return []


class ConversationStore:
    """Handles SQL database operations for conversations and leads"""
    
    def __init__(self, supabase_client):
        self.supabase = supabase_client
    
    def save_conversation(self, user_id, message, response, metadata=None):
        """Store conversation in SQL database"""
        try:
            self.supabase.table('conversations').insert({
                'user_id': user_id,
                'message': message,
                'response': response,
                'metadata': metadata or {}
            }).execute()
        except Exception as e:
            print(f"Error saving conversation: {e}")
    
    def record_user_details(self, user_id, email, name="Not provided", notes=""):
        """Record interested user details"""
        try:
            self.supabase.table('leads').insert({
                'user_id': user_id,
                'email': email,
                'name': name,
                'notes': notes
            }).execute()
            print(f"✓ Recorded lead: {email}")
            return {"recorded": "ok", "email": email}
        except Exception as e:
            print(f"Error recording user: {e}")
            return {"error": str(e)}
    
    def record_unknown_question(self, question):
        """Log questions that couldn't be answered"""
        try:
            self.supabase.table('unknown_questions').insert({
                'question': question
            }).execute()
            print(f"✓ Recorded unknown question: {question}")
            return {"recorded": "ok"}
        except Exception as e:
            print(f"Error recording question: {e}")
            return {"error": str(e)}


class AdityaChatbot:
    def __init__(self):
        self.openai = OpenAI()
        self.name = "Aditya Mazumdar"

        # Try to initialize Supabase (optional)
        self.supabase_enabled = False
        try:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_KEY")

            # Check if Supabase is properly configured
            if (supabase_url and supabase_key and
                "your-project" not in supabase_url and
                supabase_url.startswith("https://") and
                ".supabase.co" in supabase_url):

                # Try to connect
                self.supabase = create_client(supabase_url, supabase_key)

                # Test connection with a simple query
                test_result = self.supabase.table('documents').select('id').limit(1).execute()

                # If we get here, connection works
                self.rag = RAGRetriever(self.openai, self.supabase)
                self.db = ConversationStore(self.supabase)
                self.supabase_enabled = True
                print("✓ Supabase connected successfully")
            else:
                print("⚠ Supabase not configured - running without vector DB and conversation tracking")
        except Exception as e:
            print(f"⚠ Supabase connection failed - running without it")
            self.supabase_enabled = False

        # Load documents
        self.resume = self._load_resume()
        self.summary = self._load_summary()

        # Initialize vector database if Supabase is enabled
        if self.supabase_enabled:
            if not self.rag.is_initialized():
                print("Initializing vector database...")
                self.rag.embed_documents(self.resume, self.summary)
            else:
                print("✓ Vector database already initialized")
        else:
            print("✓ Chatbot ready (without Supabase features)")
    
    def _load_resume(self):
        """Load resume from PDF"""
        try:
            # Use path relative to this script's location
            base_dir = os.path.dirname(os.path.abspath(__file__))
            resume_path = os.path.join(base_dir, "Resume.pdf")
            reader = PdfReader(resume_path)
            resume = ""
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    resume += text
            return resume
        except Exception as e:
            print(f"Error reading Resume.pdf: {e}")
            return "Resume information unavailable"
    
    def _load_summary(self):
        """Load summary from text file"""
        try:
            # Use path relative to this script's location
            base_dir = os.path.dirname(os.path.abspath(__file__))
            summary_path = os.path.join(base_dir, "summary.txt")
            with open(summary_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"Error reading summary.txt: {e}")
            return ""
    
    def _get_tools(self):
        """Define available tools"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "record_user_details",
                    "description": "Record user contact details when they're interested in getting in touch",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string", "description": "User's email"},
                            "name": {"type": "string", "description": "User's name"},
                            "notes": {"type": "string", "description": "Conversation context"}
                        },
                        "required": ["email"],
                        "additionalProperties": False
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "record_unknown_question",
                    "description": "Record questions that couldn't be answered",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "The unanswered question"}
                        },
                        "required": ["question"],
                        "additionalProperties": False
                    }
                }
            }
        ]
    
    def _build_system_prompt(self, rag_context):
        """Build system prompt with RAG context"""
        base_prompt = f"""You are acting as {self.name}, a Software Development Engineer. You are answering questions on {self.name}'s portfolio website, \
particularly questions related to {self.name}'s career, background, skills, experience, and projects. \
Your responsibility is to represent {self.name} for interactions on the website as faithfully as possible. \
Be professional, engaging, and friendly, as if talking to a potential client, recruiter, or future employer who came across the website. \
Keep your responses concise and to the point - aim for 2-3 sentences unless more detail is specifically requested. \
If you don't know the answer to any question, use your record_unknown_question tool to record the question that you couldn't answer. \
If the user is engaging in discussion and seems interested in collaboration or hiring, try to steer them towards getting in touch via email; ask for their email and record it using your record_user_details tool."""
        
        # Add RAG context if available
        if rag_context:
            context_section = "\n\n## Retrieved Context:\n" + "\n\n".join(rag_context)
            base_prompt += context_section
        
        # Add full resume and summary as fallback
        if self.summary:
            base_prompt += f"\n\n## Summary:\n{self.summary}\n\n"
        if self.resume:
            base_prompt += f"## Resume:\n{self.resume}\n\n"
        
        base_prompt += f"With this context, please chat with the user, always staying in character as {self.name}. Be helpful, professional, and engaging!"
        
        return base_prompt
    
    def _handle_tool_calls(self, tool_calls, user_id):
        """Handle tool execution"""
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            print(f"Tool called: {tool_name}", flush=True)

            # Route to appropriate tool handler
            if tool_name == "record_user_details":
                if self.supabase_enabled:
                    result = self.db.record_user_details(user_id, **arguments)
                else:
                    print(f"📧 Lead captured: {arguments}")
                    result = {"recorded": "ok", "note": "Logged locally (Supabase disabled)"}
            elif tool_name == "record_unknown_question":
                if self.supabase_enabled:
                    result = self.db.record_unknown_question(**arguments)
                else:
                    print(f"❓ Unknown question: {arguments.get('question')}")
                    result = {"recorded": "ok", "note": "Logged locally (Supabase disabled)"}
            else:
                result = {"error": "Unknown tool"}

            results.append({
                "role": "tool",
                "content": json.dumps(result),
                "tool_call_id": tool_call.id
            })

        return results
    
    def chat(self, message, history, user_id="anonymous"):
        """Main chat function with RAG and tool calling"""
        # RAG: Retrieve relevant context (if Supabase enabled)
        relevant_chunks = []
        if self.supabase_enabled:
            relevant_chunks = self.rag.retrieve_context(message, top_k=3)

        # Build messages with RAG context
        messages = [{"role": "system", "content": self._build_system_prompt(relevant_chunks)}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        # Multi-turn tool calling loop
        done = False
        while not done:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=self._get_tools()
            )

            if response.choices[0].finish_reason == "tool_calls":
                message_obj = response.choices[0].message
                tool_results = self._handle_tool_calls(message_obj.tool_calls, user_id)
                messages.append(message_obj)
                messages.extend(tool_results)
            else:
                done = True

        final_response = response.choices[0].message.content

        # Store conversation in database (if Supabase enabled)
        if self.supabase_enabled:
            self.db.save_conversation(user_id, message, final_response)

        return final_response


# Initialize chatbot
print("Initializing chatbot...")
chatbot = AdityaChatbot()
print("✓ Chatbot ready!")


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '')
        history = data.get('history', [])
        user_id = data.get('user_id', 'anonymous')  # Get user ID from request
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        response = chatbot.chat(message, history, user_id)
        return jsonify({
            'response': response,
            'success': True
        })
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    # Use environment variable for port (Render uses PORT env var)
    port = int(os.getenv('PORT', 5001))
    app.run(debug=False, port=port, host='0.0.0.0')