package edu.cmu.hcii.paint;

import java.awt.*;

public class LinePaint extends PaintObject {

    private int x1, y1, x2, y2;

    public LinePaint() {
        // MUST be empty for newInstance()
    }



    @Override
    public void define(Point[] points) {

        if (points == null || points.length == 0) return;

        // Start point = first click
        x1 = points[0].x;
        y1 = points[0].y;

        // End point = latest mouse position
        x2 = points[points.length - 1].x;
        y2 = points[points.length - 1].y;
    }

    @Override
    public void paint(Graphics2D g) {
        g.setColor(color);
        g.setStroke(new BasicStroke(Math.max(thickness, 2)));
        g.drawLine(x1, y1, x2, y2);
    }

    @Override
    public double getStartX() {
        return x1;
    }

    @Override
    public double getStartY() {
        return y1;
    }

    @Override
    public double getEndX() {
        return x2;
    }

    @Override
    public double getEndY() {
        return y2;
    }

    @Override
    public Rectangle getBoundingBox() {
        int x = Math.min(x1, x2);
        int y = Math.min(y1, y2);
        int width = Math.abs(x1 - x2);
        int height = Math.abs(y1 - y2);
        return new Rectangle(x, y, width, height);
    }
}