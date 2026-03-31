import { NextResponse } from 'next/server';

export async function GET(request: Request) {
    const { searchParams } = new URL(request.url);
    const userId = searchParams.get('user_id');
    const baseUrl = process.env.BACKEND_URL;

    if (!baseUrl) {
        console.error('CRITICAL ERROR: BACKEND_URL environment variable is missing.');
        return NextResponse.json({ error: 'Internal Server Error: Missing Configuration' }, { status: 500 });
    }

    try {
        const response = await fetch(`${baseUrl}/api/chats?user_id=${userId}`, {
            cache: 'no-store'
        });
        
        if (!response.ok) {
            return NextResponse.json({ error: 'Failed to fetch chats from backend' }, { status: response.status });
        }
        
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error: any) {
        console.error('Error fetching chats:', error);
        return NextResponse.json({ 
            error: 'Internal Server Error', 
            details: error.message || String(error) 
        }, { status: 500 });
    }
}
