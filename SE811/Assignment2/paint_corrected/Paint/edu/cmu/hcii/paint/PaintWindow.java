package edu.cmu.hcii.paint;

import javax.swing.*;
import javax.swing.event.*;
import java.awt.*;
import java.awt.event.*;

public class PaintWindow extends JFrame implements PaintObjectConstructorListener {

    private PaintCanvas canvas;
    private JButton clearButton, undoButton;
    private JPanel clearUndoPanel;
    private JRadioButton pencilButton, eraserButton, lineButton;
    private JPanel toolPanel;

    private JPanel rPanel, gPanel, bPanel;
    private JSlider rSlider, gSlider, bSlider;
    private JPanel colorPanel;

    private JSlider thicknessSlider;   // ✅ thickness slider
    private JPanel thicknessPanel;     // ✅ thickness panel

    private JPanel controlPanel;
    private JScrollPane canvasPane;
    private Actions actions;

    private ButtonGroup toolButtonGroup;
    private PaintObjectConstructor objectConstructor;

    // 🎨 COLOR CHANGE LISTENER
    private ChangeListener colorChangeListener = new ChangeListener() {
        public void stateChanged(ChangeEvent changeEvent) {
            objectConstructor.setColor(new Color(
                    rSlider.getValue(),
                    gSlider.getValue(),
                    bSlider.getValue()
            ));
            repaint();
        }
    };

    // 🎨 CURRENT COLOR DISPLAY
    private JComponent currentColorComponent = new JComponent() {
        public void paintComponent(Graphics g) {
            Color oldColor = g.getColor();
            g.setColor(objectConstructor.getColor());
            g.fillRect(0, 0, getWidth(), getHeight());
            g.setColor(oldColor);
        }
    };

    public PaintWindow(int initialWidth, int initialHeight) {

        super("Paint");

        actions = new Actions(this);

        setResizable(true);
        setBackground(new Color(128, 10, 160));

        // 🖌 CANVAS
        canvas = new PaintCanvas(initialWidth, initialHeight);

        // 🔘 BUTTONS
        clearButton = new JButton(actions.clearAction);
        undoButton = new JButton(actions.undoAction);

        clearUndoPanel = new JPanel();
        clearUndoPanel.setLayout(new BoxLayout(clearUndoPanel, BoxLayout.Y_AXIS));
        clearUndoPanel.add(clearButton);
        clearUndoPanel.add(undoButton);

        // 🛠 TOOLS
        pencilButton = new JRadioButton(actions.pencilAction);
        pencilButton.setSelected(true);
        eraserButton = new JRadioButton(actions.eraserAction);
        lineButton = new JRadioButton(actions.lineAction);

        toolButtonGroup = new ButtonGroup();
        toolButtonGroup.add(pencilButton);
        toolButtonGroup.add(eraserButton);
        toolButtonGroup.add(lineButton);

        toolPanel = new JPanel();
        toolPanel.setLayout(new BoxLayout(toolPanel, BoxLayout.Y_AXIS));
        toolPanel.add(pencilButton);
        toolPanel.add(eraserButton);
        toolPanel.add(lineButton);

        // 🎨 COLOR SLIDERS
        rPanel = new JPanel();
        rPanel.add(new JLabel("Red"));
        rSlider = new JSlider(0, 255, 0);
        rSlider.addChangeListener(colorChangeListener);
        rPanel.add(rSlider);

        gPanel = new JPanel();
        gPanel.add(new JLabel("Green"));
        gSlider = new JSlider(0, 255, 255);
        gSlider.addChangeListener(colorChangeListener);
        gPanel.add(gSlider);

        bPanel = new JPanel();
        bPanel.add(new JLabel("Blue"));
        bSlider = new JSlider(0, 255, 0);
        bSlider.addChangeListener(colorChangeListener);
        bPanel.add(bSlider);

        colorPanel = new JPanel();
        colorPanel.setLayout(new BoxLayout(colorPanel, BoxLayout.Y_AXIS));
        colorPanel.add(rPanel);
        colorPanel.add(gPanel);
        colorPanel.add(bPanel);

        currentColorComponent.setPreferredSize(new Dimension(100, 50));
        colorPanel.add(currentColorComponent);

        // ✅ THICKNESS PANEL (TASK 5)
        thicknessPanel = new JPanel();
        thicknessPanel.add(new JLabel("Thickness"));

        thicknessSlider = new JSlider(1, 20, 5);
        thicknessSlider.addChangeListener(new ChangeListener() {
            public void stateChanged(ChangeEvent e) {
                objectConstructor.setThickness(thicknessSlider.getValue());
            }
        });

        thicknessPanel.add(thicknessSlider);

        // 📦 CONTROL PANEL
        controlPanel = new JPanel();
        controlPanel.setLayout(new BoxLayout(controlPanel, BoxLayout.Y_AXIS));

        controlPanel.add(toolPanel);
        controlPanel.add(colorPanel);
        controlPanel.add(thicknessPanel);   // ✅ added here
        controlPanel.add(clearUndoPanel);

        // 🖼 CANVAS SCROLL
        canvasPane = new JScrollPane(canvas);

        getContentPane().setLayout(new BorderLayout());
        getContentPane().add(canvasPane, BorderLayout.CENTER);
        getContentPane().add(controlPanel, BorderLayout.WEST);

        // 🪟 WINDOW CLOSE
        addWindowListener(new WindowAdapter() {
            public void windowClosing(WindowEvent event) {
                System.exit(0);
            }
        });

        // 🧠 OBJECT CONSTRUCTOR
        objectConstructor = new PaintObjectConstructor(this);
        objectConstructor.setClass(PencilPaint.class);
        objectConstructor.setColor(new Color(0, 255, 0));
        objectConstructor.setThickness(5);

        canvas.addMouseListener(objectConstructor);
        canvas.addMouseMotionListener(objectConstructor);

        pack();
        setVisible(true);
    }

    // 🔄 TOOL SWITCH
    public void setPaintObjectClass(Class paintObjectClass) {
        objectConstructor.setClass(paintObjectClass);
    }

    // ↩ UNDO
    public void undo() {
        canvas.undo();
        if (canvas.sizeOfHistory() == 0)
            actions.undoAction.setEnabled(false);
    }

    // 🧹 CLEAR
    public void clear() {
        canvas.clear();
    }

    // 🧱 CONSTRUCTION EVENTS
    public void constructionBeginning(PaintObject temporaryObject) {
        canvas.setTemporaryObject(temporaryObject);
    }

    public void constructionContinuing(PaintObject temporaryObject) {
        canvas.setTemporaryObject(temporaryObject);
    }

    public void constructionComplete(PaintObject finalObject) {
        canvas.setTemporaryObject(null);
        canvas.addPaintObject(finalObject);
        actions.undoAction.setEnabled(true);
    }

    public void hoveringOverConstructionArea(PaintObject hoverObject) {
        canvas.setHoveringObject(hoverObject);
    }

    public static void main(String[] args) {
        new PaintWindow(800, 600);
    }
}