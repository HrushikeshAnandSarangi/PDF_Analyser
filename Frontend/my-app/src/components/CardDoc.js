'use client'
import React, { useState, useRef, useCallback, useEffect } from 'react';
import axios from 'axios';
import { AlertCircle, FileText, Loader2 } from 'lucide-react';

const ALLOWED_FILE_TYPES = {
  'application/pdf': 'PDF',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
  'text/plain': 'TXT',
  'text/csv': 'CSV'
};

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

export default function CardDoc() {
    const [file, setFile] = useState(null);
    const [question, setQuestion] = useState('');
    const [chatHistory, setChatHistory] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const chatContainerRef = useRef(null);
    const fileInputRef = useRef(null);

    const api = axios.create({
        baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
        timeout: 30000,
    });

    const validateFile = (uploadedFile) => {
        if (!Object.keys(ALLOWED_FILE_TYPES).includes(uploadedFile.type)) {
            return `Invalid file type. Please upload ${Object.values(ALLOWED_FILE_TYPES).join(', ')} files only.`;
        }

        if (uploadedFile.size > MAX_FILE_SIZE) {
            return 'File size exceeds 10MB limit.';
        }

        return null;
    };

    const handleFileUpload = useCallback(async (e) => {
        const uploadedFile = e.target.files?.[0];
        if (!uploadedFile) return;

        const validationError = validateFile(uploadedFile);
        if (validationError) {
            setError(validationError);
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
            return;
        }

        const formData = new FormData();
        formData.append('file', uploadedFile);

        setIsLoading(true);
        setError('');

        try {
            await api.post('/upload', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });
            setFile(uploadedFile);
            setChatHistory([]); // Clear chat history when new file is uploaded
            setError('');
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred while uploading the file.';
            setError(`Error uploading file: ${errorMessage}`);
            setFile(null);
        } finally {
            setIsLoading(false);
        }
    }, [api]);

    const handleQuestionSubmit = useCallback(async (e) => {
        e.preventDefault();
        const trimmedQuestion = question.trim();
        
        if (!trimmedQuestion || !file) return;

        setIsLoading(true);
        setError('');

        try {
            const response = await api.post('/ask', {
                question: trimmedQuestion,
                chat_history: chatHistory
            });

            const newMessage = {
                question: trimmedQuestion,
                answer: response.data.answer,
                context: response.data.context,
                id: crypto.randomUUID()
            };

            setChatHistory(prev => [...prev, newMessage]);
            setQuestion('');
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Failed to get answer. Please try again.';
            setError(`Error: ${errorMessage}`);
        } finally {
            setIsLoading(false);
        }
    }, [question, file, chatHistory, api]);

    // Scroll to bottom when chat history updates
    useEffect(() => {
        if (chatContainerRef.current) {
            const element = chatContainerRef.current;
            element.scrollTop = element.scrollHeight;
        }
    }, [chatHistory]);

    return (
        <div className="min-h-screen bg-gray-100 p-4">
            <div className="max-w-4xl mx-auto">
                <div className="bg-white rounded-lg shadow-lg p-6 mb-4">
                    <h1 className="text-2xl font-bold mb-4">Document Q&A System</h1>
                    
                    <div className="mb-6">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Upload Document ({Object.values(ALLOWED_FILE_TYPES).join(', ')})
                        </label>
                        <div className="flex items-center space-x-2">
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept={Object.keys(ALLOWED_FILE_TYPES).join(',')}
                                onChange={handleFileUpload}
                                className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 
                                         file:rounded-full file:border-0 file:text-sm file:font-semibold 
                                         file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                                disabled={isLoading}
                            />
                            {file && (
                                <div className="flex items-center text-sm text-gray-600">
                                    <FileText className="w-4 h-4 mr-1" />
                                    {file.name}
                                </div>
                            )}
                        </div>
                    </div>

                    <div
                        ref={chatContainerRef}
                        className="bg-gray-50 rounded-lg p-4 mb-4 h-96 overflow-y-auto"
                    >
                        {chatHistory.length === 0 ? (
                            <div className="text-center text-gray-500 mt-32">
                                Upload a document and ask questions to get started
                            </div>
                        ) : (
                            chatHistory.map((message) => (
                                <div key={message.id} className="mb-4">
                                    <div className="font-semibold text-blue-600 mb-1">
                                        Q: {message.question}
                                    </div>
                                    <div className="ml-4 mb-2">
                                        A: {message.answer}
                                    </div>
                                    <div className="ml-4 text-sm text-gray-600 bg-gray-100 p-2 rounded">
                                        <div className="font-medium mb-1">Relevant Context:</div>
                                        {message.context.map((ctx, idx) => (
                                            <div 
                                                key={`${message.id}-${idx}`} 
                                                className="mb-1 pl-2 border-l-2 border-gray-300"
                                            >
                                                {ctx}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            ))
                        )}
                    </div>

                    <form onSubmit={handleQuestionSubmit} className="flex gap-2">
                        <input
                            type="text"
                            value={question}
                            onChange={(e) => setQuestion(e.target.value)}
                            placeholder="Ask a question about the document..."
                            className="flex-1 rounded-lg border border-gray-300 px-4 py-2 
                                     focus:outline-none focus:ring-2 focus:ring-blue-500"
                            disabled={!file || isLoading}
                        />
                        <button
                            type="submit"
                            disabled={!file || isLoading || !question.trim()}
                            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 
                                     disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center"
                        >
                            {isLoading ? (
                                <>
                                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                    Loading...
                                </>
                            ) : 'Send'}
                        </button>
                    </form>

                    {error && (
                        <div
                            className="mt-4 p-4 border border-red-200 bg-red-50 rounded-lg flex items-center text-red-700"
                            role="alert"
                            aria-live="assertive"
                        >
                            <AlertCircle className="h-4 w-4 mr-2 flex-shrink-0" />
                            <span className="text-sm">{error}</span>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
