import { NextResponse } from 'next/server';

export async function GET(request: Request) {
    const baseUrl = process.env.BACKEND_URL;
    const { searchParams } = new URL(request.url);
    const userId = searchParams.get('user_id');

    if (!baseUrl) {
        return NextResponse.json({ error: 'Missing Configuration' }, { status: 500 });
    }

    try {
        const response = await fetch(`${baseUrl}/api/debug/documents?user_id=${userId || ''}`, {
            method: 'GET',
        });

        const data = await response.json();
        return NextResponse.json(data, { status: response.status });
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
