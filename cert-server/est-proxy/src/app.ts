import express from "express";
import estRoutes from "./routes/estRoutes";

const app = express();
app.use(express.raw({ type: "*/*", limit: "2mb" }));
app.use("/", estRoutes);

export default app;