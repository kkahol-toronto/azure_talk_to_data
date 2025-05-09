import React, { useState, useRef, useEffect } from 'react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  audio?: string;
  transcription?: string;
  files?: {
    original_audio: string;
    transcription: string;
    tts_audio: string;
  };
}

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const playAudioResponse = (audioHex: string) => {
    // Convert hex to binary
    const binary = new Uint8Array(audioHex.match(/.{1,2}/g)!.map(byte => parseInt(byte, 16)));
    const blob = new Blob([binary], { type: 'audio/wav' });
    const url = URL.createObjectURL(blob);
    
    if (audioPlayerRef.current) {
      audioPlayerRef.current.src = url;
      audioPlayerRef.current.play();
    }
  };

  const startConversation = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data);
      };

      mediaRecorderRef.current.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        await processAudio(audioBlob);
      };

      mediaRecorderRef.current.start();
      setIsListening(true);
    } catch (error) {
      console.error('Error accessing microphone:', error);
    }
  };

  const stopConversation = () => {
    if (mediaRecorderRef.current && isListening) {
      mediaRecorderRef.current.stop();
      setIsListening(false);
    }
  };

  const processAudio = async (audioBlob: Blob) => {
    setIsProcessing(true);
    try {
      const formData = new FormData();
      formData.append('audio', audioBlob);

      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Failed to process audio');
      }

      const data = await response.json();
      setMessages(prev => [...prev, 
        { role: 'user', content: data.transcription || 'Transcription not available', transcription: data.transcription, files: data.files },
        { role: 'assistant', content: data.response, audio: data.audio }
      ]);

      // Play the audio response
      if (data.audio) {
        playAudioResponse(data.audio);
      }
    } catch (error) {
      console.error('Error processing audio:', error);
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'Sorry, there was an error processing your message.' 
      }]);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      <div className="flex-1 container mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow-lg p-6 h-[600px] flex flex-col">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`flex ${
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                <div
                  className={`max-w-[70%] rounded-lg p-3 ${
                    message.role === 'user'
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-200 text-gray-800'
                  }`}
                >
                  {message.role === 'user' ? (
                    <p>{message.transcription || message.content}</p>
                  ) : (
                    <>
                      <p>{message.content}</p>
                      {message.transcription && (
                        <div className="mt-2 text-sm">
                          <p className="font-semibold">Transcription:</p>
                          <p className="italic">{message.transcription}</p>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
          
          <div className="flex justify-center space-x-4">
            {!isListening ? (
              <button
                onClick={startConversation}
                disabled={isProcessing}
                className="bg-green-500 hover:bg-green-600 text-white px-6 py-2 rounded-full transition-colors disabled:opacity-50"
              >
                Start Conversation
              </button>
            ) : (
              <button
                onClick={stopConversation}
                className="bg-red-500 hover:bg-red-600 text-white px-6 py-2 rounded-full transition-colors"
              >
                Stop Conversation
              </button>
            )}
          </div>
          
          {isProcessing && (
            <div className="text-center mt-4 text-gray-600">
              Processing your message...
            </div>
          )}

          <audio ref={audioPlayerRef} className="hidden" />
        </div>
      </div>
    </div>
  );
}

export default App; 