import { AzureFunction, Context, HttpRequest } from "@azure/functions";
import { OpenAIClient } from "@azure/openai";

const httpTrigger: AzureFunction = async function (context: Context, req: HttpRequest): Promise<void> {
    try {
        const audioBlob = req.body;
        
        // Initialize OpenAI client
        const client = new OpenAIClient(
            process.env["AZURE_OPENAI_ENDPOINT"] || "",
            {
                apiKey: process.env["AZURE_OPENAI_API_KEY"]
            }
        );

        // Convert audio to text using Azure OpenAI Whisper
        const transcriptionResponse = await client.getAudioTranscription(
            process.env["AZURE_OPENAI_DEPLOYMENT_NAME"] || "",
            audioBlob
        );

        // Get response from OpenAI
        const completionResponse = await client.getChatCompletions(
            process.env["AZURE_OPENAI_DEPLOYMENT_NAME"] || "",
            [
                {
                    role: "system",
                    content: "You are a helpful assistant that engages in natural conversation."
                },
                {
                    role: "user",
                    content: transcriptionResponse.text
                }
            ]
        );

        context.res = {
            status: 200,
            body: {
                response: completionResponse.choices[0].message?.content
            }
        };
    } catch (error) {
        context.res = {
            status: 500,
            body: {
                error: "An error occurred while processing your request."
            }
        };
    }
};

export default httpTrigger; 