import { UIMessage } from 'ai';

// Define your custom message type with data part schemas
export type MyUIMessage = UIMessage<
    never, // metadata type
    {
        status: {
            message?: string;
            thread_id?: string;
        };
    } // data parts type
>;