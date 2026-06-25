import { Router, type IRouter } from "express";
import healthRouter from "./health";
import dashboardRouter from "./dashboard";
import stocksRouter from "./stocks";
import institutionalRouter from "./institutional";
import insidersRouter from "./insiders";
import politiciansRouter from "./politicians";
import lockupsRouter from "./lockups";

const router: IRouter = Router();

router.use(healthRouter);
router.use(dashboardRouter);
router.use(stocksRouter);
router.use(institutionalRouter);
router.use(insidersRouter);
router.use(politiciansRouter);
router.use(lockupsRouter);

export default router;
