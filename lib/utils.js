'use server';
import mongoose from 'mongoose';

let connection = {};

export const connectToDB = async () => {
  if (connection.isConnected && mongoose.connection.readyState === 1) {
    console.log('Already connected to MongoDB');
    return;
  }

  const maxRetries = 3;
  let lastError;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      console.log(`MongoDB connection attempt ${attempt}/${maxRetries}`);
      
      const db = await mongoose.connect(process.env.MONGO, {
        serverSelectionTimeoutMS: 30000, 
        socketTimeoutMS: 45000,
        connectTimeoutMS: 30000,
      });

      await mongoose.connection.db.admin().command({ ping: 1 });

      connection.isConnected = true;
      console.log('Successfully connected to MongoDB');
      return;
      
    } catch (error) {
      lastError = error;
      console.error(`MongoDB connection attempt ${attempt} failed:`, error.message);
      
      connection.isConnected = false;
      
      if (attempt < maxRetries) {
        const waitTime = Math.min(1000 * Math.pow(2, attempt - 1), 10000);
        console.log(`Waiting ${waitTime}ms before retry...`);
        await new Promise(resolve => setTimeout(resolve, waitTime));
      }
    }
  }

  console.error('All MongoDB connection attempts failed');
  throw new Error(`MongoDB connection failed after ${maxRetries} attempts: ${lastError.message}`);
};