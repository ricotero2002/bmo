import { NextResponse } from 'next/server';

export async function POST(request: Request) {
    const baseUrl = process.env.BACKEND_URL;

    if (!baseUrl) {
        return NextResponse.json({ error: 'Internal Server Error: Missing Configuration' }, { status: 500 });
    }

    try {
        const formData = await request.formData();
        
        // El backend espera 'file' y opcionalmente 'user_id'
        const response = await fetch(`${baseUrl}/api/ingest`, {
            method: 'POST',
            body: formData,
        });

        const data = await response.json();
        return NextResponse.json(data, { status: response.status });
    } catch (error: any) {
        console.error('Error in ingest proxy:', error);
        return NextResponse.json({ 
            error: 'Failed to upload file', 
            details: error.message || String(error)
        }, { status: 500 });
    }
}
