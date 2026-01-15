---
title: career_assistant
app_file: chatbot_api.py
sdk: gradio
sdk_version: 5.49.1
---
# Chatbot API Setup

This is the Flask backend API that powers the AI chatbot on your portfolio website.

## Setup Instructions

1. **Install Python dependencies:**
   ```bash
   cd api
   pip install -r requirements.txt
   ```

2. **Create a `.env` file:**
   ```bash
   cp .env.example .env
   ```

3. **Add your OpenAI API key to `.env`:**
   ```
   OPENAI_API_KEY=your_actual_api_key_here
   ```

4. **Run the API server:**
   ```bash
   python chatbot_api.py
   ```

   The API will start on `http://localhost:5000`

## API Endpoints

- `POST /api/chat` - Send a message to the chatbot
  - Request body: `{ "message": "string", "history": [] }`
  - Response: `{ "response": "string", "success": true }`

- `GET /api/health` - Check if the API is running
  - Response: `{ "status": "healthy" }`

## Usage

Make sure both the React frontend (port 5173) and Flask backend (port 5000) are running:

1. Terminal 1: `npm run dev` (in portfolio directory)
2. Terminal 2: `python chatbot_api.py` (in api directory)

Then open http://localhost:5173 and click the chatbot button in the bottom right corner!
