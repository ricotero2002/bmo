import { NextResponse } from 'next/server';

export async function POST(request: Request) {
    const baseUrl = process.env.BACKEND_URL;

    if (!baseUrl) {
        return NextResponse.json({ error: 'Missing Configuration' }, { status: 500 });
    }

    try {
        const body = await request.json();
        const response = await fetch(`${baseUrl}/api/delete_file`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        });

        const data = await response.json();
        return NextResponse.json(data, { status: response.status });
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
